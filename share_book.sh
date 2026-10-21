
#!/bin/bash
set -euo pipefail

if [ "$#" -ne 3 ]; then
    echo "Usage: ./share_book.sh BOOK_URL BUCKET_NAME EXPIRATION_SECONDS"
    exit 1
fi

BOOK_URL="$1"
BUCKET="$2"
EXPIRATION="$3"

if ! [[ "$EXPIRATION" =~ ^[0-9]+$ ]] || [ "$EXPIRATION" -lt 1 ]; then
    echo "Error: expiration must be a positive integer."
    exit 1
fi

FILENAME="$(basename "${BOOK_URL%%\?*}")"
mkdir -p books

echo "Downloading $FILENAME..."
curl --fail --location --output "books/$FILENAME" "$BOOK_URL"

if aws s3 ls "s3://$BUCKET" >/dev/null 2>&1; then
    echo "Bucket already exists: $BUCKET"
else
    echo "Creating private bucket: $BUCKET"
    aws s3 mb "s3://$BUCKET" --region us-east-1
fi

echo "Uploading book..."
aws s3 cp "books/$FILENAME" "s3://$BUCKET/$FILENAME" \
    --content-type "text/plain; charset=utf-8"

echo "Generating temporary link..."
PRESIGNED_URL="$(aws s3 presign "s3://$BUCKET/$FILENAME" \
    --expires-in "$EXPIRATION")"

echo "Upload successful!"
echo "Presigned URL (keep it private):"
echo "$PRESIGNED_URL"
