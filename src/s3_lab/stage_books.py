#!/usr/bin/env python3
"""Download Project Gutenberg books and stage them in a public S3 bucket."""

import json
import logging
import os
import sys
import time
from urllib.parse import urlparse

import boto3
import requests
from botocore.exceptions import ClientError

# Configure logging and create one shared S3 client.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)
s3 = boto3.client("s3", region_name="us-east-1")


def parse_args():
    """Read the book list, index page, and bucket name."""
    if len(sys.argv) != 4:
        log.error(
            "Usage: stage_books.py BOOK_LIST INDEX_HTML BUCKET_NAME"
        )
        sys.exit(1)

    return sys.argv[1], sys.argv[2], sys.argv[3]


def download_books(list_file, dest_dir):
    """Download books from the URL list and return their local paths."""
    os.makedirs(dest_dir, exist_ok=True)
    downloaded = []

    try:
        with open(list_file, encoding="utf-8") as file:
            urls = [line.strip() for line in file if line.strip()]
    except OSError as error:
        log.error("Could not read %s: %s", list_file, error)
        return downloaded

    for url in urls:
        filename = os.path.basename(urlparse(url).path)
        if not filename:
            log.error("Could not determine filename for %s", url)
            continue

        path = os.path.join(dest_dir, filename)

        if os.path.exists(path):
            log.info("Already downloaded; skipping %s", filename)
            downloaded.append(path)
            continue

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            with open(path, "wb") as file:
                file.write(response.content)
            downloaded.append(path)
            log.info("Downloaded %s", filename)
        except (requests.RequestException, OSError) as error:
            log.error("Could not download %s: %s", url, error)

        time.sleep(1)

    return downloaded


def create_bucket(bucket):
    """Create the S3 bucket if it does not already exist."""
    try:
        s3.head_bucket(Bucket=bucket)
        log.info("Bucket %s already exists and is accessible", bucket)
        return True
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "")
        if code not in ("404", "NoSuchBucket", "NotFound"):
            log.error("Cannot access bucket %s: %s", bucket, error)
            return False

    try:
        s3.create_bucket(Bucket=bucket)
        log.info("Created bucket %s", bucket)
        return True
    except ClientError as error:
        log.error("Could not create bucket %s: %s", bucket, error)
        return False


def make_public(bucket):
    """Allow public reads of objects in the bucket."""
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{bucket}/*",
            }
        ],
    }

    try:
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": False,
                "IgnorePublicAcls": False,
                "BlockPublicPolicy": False,
                "RestrictPublicBuckets": False,
            },
        )
        s3.put_bucket_policy(
            Bucket=bucket,
            Policy=json.dumps(policy),
        )
        log.info("Bucket %s is configured for public reads", bucket)
        return True
    except ClientError as error:
        log.error("Could not make bucket public: %s", error)
        return False


def upload_files(bucket, file_paths):
    """Upload book files as plain text and return the success count."""
    count = 0

    for path in file_paths:
        filename = os.path.basename(path)
        try:
            s3.upload_file(
                path,
                bucket,
                filename,
                ExtraArgs={"ContentType": "text/plain; charset=utf-8"},
            )
            count += 1
            log.info("Uploaded %s", filename)
        except (ClientError, OSError) as error:
            log.error("Could not upload %s: %s", filename, error)

    return count


def upload_index(bucket, index_path):
    """Upload the HTML index page."""
    try:
        s3.upload_file(
            index_path,
            bucket,
            "index.html",
            ExtraArgs={"ContentType": "text/html"},
        )
        log.info("Uploaded index.html")
        return True
    except (ClientError, OSError) as error:
        log.error("Could not upload index: %s", error)
        return False


def main():
    """Download books, configure the bucket, and upload the collection."""
    list_file, index_path, bucket = parse_args()

    if not os.path.isfile(index_path):
        log.error("Index file does not exist: %s", index_path)
        sys.exit(1)

    books = download_books(list_file, "books")
    if not books:
        log.error("No books were downloaded or found locally.")
        sys.exit(1)

    if not create_bucket(bucket):
        sys.exit(1)

    if not make_public(bucket):
        sys.exit(1)

    uploaded = upload_files(bucket, books)
    index_uploaded = upload_index(bucket, index_path)

    if uploaded != len(books) or not index_uploaded:
        log.error("Some files failed to upload. Review the errors above.")
        sys.exit(1)

    log.info("Successfully staged %s books.", uploaded)
    log.info("Public index: https://%s.s3.amazonaws.com/index.html", bucket)


if __name__ == "__main__":
    main()
