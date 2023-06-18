import random

# установка "зерна" датчика случайных чисел, чтобы получались одни и те же случайные величины
random.seed(1)
# начальная инициализация поля (переменные P и N не менять, единицы записывать в список P)
N = int(input())
P = [[0] * N for i in range(N)]


# здесь продолжайте программу
def allnulls(i, j):
    sum = 0
    for a in range(i - 1, i + 2):
        for b in range(j - 1, j + 2):
            if not ((a == i) and (b == j)) and (0 <= a < N) and (0 <= b < N):
                sum += P[a][b]
    return bool(sum)


M = 10
t = 0
while t < M:
    a = random.randint(0, N - 1)
    b = random.randint(0, N - 1)
    if (not allnulls(a, b))and(P[a][b] != 1):
        P[a][b] = 1
        t += 1
for i in P:
    print(*i)
