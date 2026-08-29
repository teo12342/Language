FIB=27
BS=600
BENCH=1

def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


def make_list(n, seed):
    lst = []
    x = seed
    for i in range(n):
        x = (x * 1103515245 + 12345) % 2147483648
        lst.append(x % 10000)
    return lst


def bubble_sort(lst):
    n = len(lst)
    i = 0
    while i < n:
        j = 0
        while j < n - i - 1:
            if lst[j] > lst[j + 1]:
                tmp = lst[j]
                lst[j] = lst[j + 1]
                lst[j + 1] = tmp
            j = j + 1
        i = i + 1
    return lst


def word_count(text):
    words = text.split(" ")
    counts = {}
    for w in words:
        counts[w] = 0
    for w in words:
        counts[w] = counts[w] + 1
    return counts


text = "the quick brown fox jumps over the lazy dog the fox runs the dog barks the fox hides"

print("fib(27) =", fib(FIB))

sorted_list = bubble_sort(make_list(BS, 42))
print("sorted first 5:", [sorted_list[0], sorted_list[1], sorted_list[2], sorted_list[3], sorted_list[4]])
print("sorted last:", sorted_list[len(sorted_list) - 1])

counts = word_count(text)
print("word 'the' count:", counts["the"])
print("word 'fox' count:", counts["fox"])
