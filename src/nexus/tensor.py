class Tensor:
    """A dense 1-D or 2-D numeric array with elementwise ops."""

    __slots__ = ("shape", "data")

    def __init__(self, shape, data: list[float]):
        self.shape = tuple(shape)
        self.data = data

    @staticmethod
    def from_nested(nested: list) -> "Tensor":
        if not nested:
            return Tensor((0,), [])
        if isinstance(nested[0], list):
            rows = len(nested)
            cols = len(nested[0])
            data = []
            for row in nested:
                if len(row) != cols:
                    raise ValueError("tensor() rows must all be the same length")
                data.extend(float(v) for v in row)
            return Tensor((rows, cols), data)
        return Tensor((len(nested),), [float(v) for v in nested])

    def to_nested(self):
        if len(self.shape) == 1:
            return list(self.data)
        rows, cols = self.shape
        return [self.data[r * cols:(r + 1) * cols] for r in range(rows)]

    def _elementwise(self, other, op) -> "Tensor":
        if isinstance(other, Tensor):
            if other.shape != self.shape:
                raise ValueError(f"shape mismatch: {self.shape} vs {other.shape}")
            return Tensor(self.shape, [op(a, b) for a, b in zip(self.data, other.data)])
        return Tensor(self.shape, [op(a, other) for a in self.data])

    def __add__(self, other):
        return self._elementwise(other, lambda a, b: a + b)

    def __sub__(self, other):
        return self._elementwise(other, lambda a, b: a - b)

    def __mul__(self, other):
        return self._elementwise(other, lambda a, b: a * b)

    def __truediv__(self, other):
        return self._elementwise(other, lambda a, b: a / b)

    def __eq__(self, other):
        return isinstance(other, Tensor) and self.shape == other.shape and self.data == other.data

    def __repr__(self):
        return f"tensor{self.to_nested()!r}"

    __str__ = __repr__


def dot(a: Tensor, b: Tensor) -> float:
    if len(a.shape) != 1 or len(b.shape) != 1 or a.shape != b.shape:
        raise ValueError("dot() requires two equal-length 1-D tensors")
    return sum(x * y for x, y in zip(a.data, b.data))


def matmul(a: Tensor, b: Tensor) -> Tensor:
    if len(a.shape) != 2 or len(b.shape) != 2 or a.shape[1] != b.shape[0]:
        raise ValueError("matmul() requires shapes (m,k) and (k,n)")
    m, k = a.shape
    _, n = b.shape
    result = [0.0] * (m * n)
    for i in range(m):
        for j in range(n):
            s = 0.0
            for t in range(k):
                s += a.data[i * k + t] * b.data[t * n + j]
            result[i * n + j] = s
    return Tensor((m, n), result)
