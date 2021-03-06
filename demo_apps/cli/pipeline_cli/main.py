import argparse

import parsl
from parsl.executors import ThreadPoolExecutor
from parsl.executors import HighThroughputExecutor
from parsl.providers import LocalProvider
from parsl.config import Config

from colmena.redis.queue import MethodServerQueues
from colmena.method_server import ParslMethodServer


# Hard code the function to be optimized
def target_fun(x: float) -> float:
    return (x - 1) * (x - 2)


def cli_run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redishost", default="127.0.0.1",
                        help="Address at which the redis server can be reached")
    parser.add_argument("--redisport", default="6379",
                        help="Port on which redis is available")
    parser.add_argument("-d", "--debug", action='store_true',
                        help="Count of apps to launch")
    parser.add_argument("-m", "--mac", action='store_true',
                        help="Configure for Mac")
    args = parser.parse_args()

    if args.debug:
        parsl.set_stream_logger()

    if args.mac:
        config = Config(
            executors=[
                ThreadPoolExecutor(label="htex"),
                ThreadPoolExecutor(label="local_threads")
            ],
            strategy=None,
        )
    else:
        config = Config(
            executors=[
                HighThroughputExecutor(
                    label="htex",
                    # Max workers limits the concurrency exposed via mom node
                    max_workers=2,
                    provider=LocalProvider(
                        init_blocks=1,
                        max_blocks=1,
                    ),
                ),
                ThreadPoolExecutor(label="local_threads")
            ],
            strategy=None,
        )
    parsl.load(config)

    print('''This program creates an "MPI Method Server" that listens on an inputs queue and write on an output queue:

        input_queue --> mpi_method_server --> queues

To send it a request, add an entry to the inputs queue:
     run "pipeline-pump -p N" where N is an integer request
To access a value, remove it from the outout queue:
     run "pipeline-pull" (blocking) or "pipeline-pull -t T" (T an integer) to time out after T seconds
     TODO: Timeout does not work yet!
''')

    # Get the queues for the method server
    method_queues = MethodServerQueues(args.redishost, port=args.redisport)

    # Start the method server
    mms = ParslMethodServer([target_fun], method_queues, default_executors=['htex'])
    mms.run()


if __name__ == "__main__":
    cli_run()
