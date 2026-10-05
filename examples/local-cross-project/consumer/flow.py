from weavem import flow, task

double = task("demo.double", "1.0.0")
native_double = task("demo.native_double", "1.0.0")


@flow
def demo():
    return double(21), native_double(21)


if __name__ == "__main__":
    result = demo()
    assert result == (42, 42), result
    print(result)
