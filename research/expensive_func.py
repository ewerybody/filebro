import time
import typing
import multiprocessing


def expensive_func(n: int) -> int:
    print(f'expensive_func: {n} running in {multiprocessing.current_process().name}')
    time.sleep(2)
    # for _ in range(200_000):
    #     n *= 2
    return n


def single_process(numbers: list[int]) -> list[int]:
    return [expensive_func(n) for n in numbers]

def multi_process(numbers: list[int]) -> list[int]:
    with multiprocessing.Pool() as pool:
        return pool.map(expensive_func, numbers)


def timeit(func: typing.Callable, *args: typing.Any) -> float:
    t0 = time.perf_counter()
    func(*args)
    t1 = time.perf_counter() - t0
    print(f'{func.__name__} took: {t1:.3f}s')
    return t1


def main():
    print(f'CPUs: {multiprocessing.cpu_count()}')

    numbers = list(range(1, 3))

    t_single = timeit(single_process, numbers)
    t_multi =  timeit(multi_process, numbers)

    print(f'factor: {t_single / t_multi:.2f}x')



if __name__ == '__main__':
    main()