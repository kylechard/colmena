import argparse
from multiprocessing import Queue
import redis
import time
import os

import parsl
from parsl import python_app, bash_app
from parsl.executors import ThreadPoolExecutor
from parsl.executors import HighThroughputExecutor
from parsl.providers import LocalProvider
from parsl.config import Config
from parsl.data_provider.files import File
from concurrent.futures import Future

from redis_q import RedisQueue

class MpiMethodServer:

    def __init__(self, input_queue, output_queue):
        self.input_queue  = input_queue
        self.output_queue = output_queue
        self.task_list    = []

    # Simulate will run some commands on bash, this can be made to run MPI applications via aprun
    # Here, simulate will put a random number from range(0-32767) into the output file.
    # ************ NOTE: Seems that a bash_app cannot take a "self", so I need to remove
    @bash_app(executors=['theta_mpi_launcher'])
    def simulate(params, delay=1, outputs=[], stdout=parsl.AUTO_LOGNAME, stderr=parsl.AUTO_LOGNAME):
        return f'''sleep {delay};
        echo "Running at ", $PWD
        echo "Running some serious MPI application"
        set -x
        echo "aprun mpi_application {params} -o {outputs[0]}"
        echo $RANDOM > {outputs[0]}
        '''

    # Output the param and output kv pair on the output queue.
    # This app runs on the Parsl local side on threads.
    # ************ NOTE: Seems that a python_app cannot take a "self", so I need to remove, and pass output_queue through also
    @python_app(executors=['local_threads'])
    def output_result(output_queue, param, inputs=[]):
        print('Output result', param)
        with open(inputs[0]) as f:
            simulated_output = int(f.readline().strip())
            print(f"Outputting {param} : {simulated_output}")
            output_queue.put((param, simulated_output))
        return param, simulated_output

    # We listen on a Python multiprocessing Queue as an example
    # we launch the application with the params that arrive over this queue
    # Listen on the input queue for params, run a task for the param, and output the result on output queue
    # ************ NOTE: Oddly this python_app CAN take a self
    @python_app(executors=['local_threads'])
    def listen_and_launch(self):
        while True:
            param = self.input_queue.get()
            if param is None:
                break
            future = self.run_application(param)
            self.task_list.append(future)
        return self.task_list


    def make_outdir(self, path):
        # Make outputs directory if it does not already exist
        if not os.path.exists(path):
            os.makedirs(path)


    # Calls a function (remotely) and add result to output queue
    def run_application(self, i):
        print(f"Run_application called with {i} \n")
        outdir = 'outputs'
        self.make_outdir(outdir)
        x = self.simulate(i, delay=1 + int(i) % 2, outputs=[File(f'{outdir}/simulate_{i}.out')])
        y = self.output_result(self.output_queue, i, inputs=[x.outputs[0]])
        return y


    def main_loop(self):
        m = self.listen_and_launch(self)
        print(m.result())
        for task in self.task_list:
            current = task
            print('Task:',current)
            while True:
                x = current.result()
                if isinstance(x, Future):
                    current = x
                else:
                    break
        dfk = parsl.dfk()
        dfk.wait_for_current_tasks()
