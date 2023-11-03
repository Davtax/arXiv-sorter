import filecmp
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('fileA')
parser.add_argument('fileB')
parser.add_argument('fileC')

args = parser.parse_args()

print(filecmp.cmp(args.fileA, args.fileB))
print(filecmp.cmp(args.fileB, args.fileC))
