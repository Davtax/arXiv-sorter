import filecmp
import argparse
import difflib

parser = argparse.ArgumentParser()
parser.add_argument('fileA')
parser.add_argument('fileB')
parser.add_argument('fileC')

args = parser.parse_args()

contentA = open(args.fileA, 'r').readlines()
contentB = open(args.fileB, 'r').readlines()
contentC = open(args.fileC, 'r').readlines()

diff = difflib.ndiff(contentA, contentB)
print('\n'.join(list(diff)))

print(filecmp.cmp(args.fileA, args.fileB))
print(filecmp.cmp(args.fileB, args.fileC))
