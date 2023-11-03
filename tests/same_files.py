import sys

names = sys.argv[1:]

content = [open(name, 'r').readlines() for name in names]
content = sorted(content, key=len)

for i in range(len(content) - 1):
    DF = [x for x in content[i] if x not in content[i + 1]]

    if DF:
        print(f'The following lines are different from machines {DF}')
        sys.exit(1)
