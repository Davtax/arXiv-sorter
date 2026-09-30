#!/bin/bash
# Installs (or updates) the latest arXiv-sorter-GUI-macOS.app, without the Gatekeeper warning:
#
#   curl -fsSL https://raw.githubusercontent.com/Davtax/arXiv-sorter/main/scripts/install_macos.sh | bash
#
# The app is not notarized by Apple (that needs a paid developer account), so macOS blocks it when it is downloaded with
# a browser, which marks the file as quarantined. curl does not add that mark, so the app downloaded here opens directly.
# Its ad-hoc signature is kept, and the archive is checked against the SHA256SUMS.txt of the release.
#
# By default the app goes to the current folder (the keyword files and the abstracts are kept next to it). Choose
# another folder with `bash -s -- <folder>` after the pipe, or with ARXIV_SORTER_DIR=<folder>. A previous version in
# that folder is replaced, and the files next to it are not touched.
set -euo pipefail

repo=Davtax/arXiv-sorter
app=arXiv-sorter-GUI-macOS.app
archive=arXiv-sorter-GUI-macOS.zip
url="https://github.com/$repo/releases/latest/download"
destination=${1:-${ARXIV_SORTER_DIR:-$PWD}}

if [ "$(uname -s)" != Darwin ]; then
  echo "This script is for macOS. See https://github.com/$repo/releases for the other systems." >&2
  exit 1
fi
if [ "$(uname -m)" != arm64 ]; then
  echo "The macOS app is built for Apple silicon (arm64), and this Mac is $(uname -m)." >&2
  exit 1
fi

mkdir -p "$destination"
destination=$(cd "$destination" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

echo "Downloading the latest $archive..."
curl -fsSL -o "$work/$archive" "$url/$archive"
curl -fsSL -o "$work/SHA256SUMS.txt" "$url/SHA256SUMS.txt"

(cd "$work" && grep " $archive\$" SHA256SUMS.txt | shasum -a 256 -c -s) || {
  echo "The checksum of $archive does not match SHA256SUMS.txt, so it was not installed." >&2
  exit 1
}

ditto -x -k "$work/$archive" "$work/extracted"
# Just in case: an archive downloaded before with a browser and passed along keeps the quarantine mark
xattr -dr com.apple.quarantine "$work/extracted/$app" 2>/dev/null || true
codesign --verify --deep --strict "$work/extracted/$app"

rm -rf "${destination:?}/$app"
mv "$work/extracted/$app" "$destination/"
echo "Installed $destination/$app"
echo "Open it with: open \"$destination/$app\""
