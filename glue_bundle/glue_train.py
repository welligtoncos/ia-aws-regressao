"""Entrypoint Glue Python Shell — carrega bundle flat de S3 antes dos imports."""

import io
import sys
import tempfile
import zipfile


def _resolve_input_bucket():
    for i, arg in enumerate(sys.argv):
        if arg == "--INPUT_BUCKET" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def _load_bundle():
    try:
        import train_pipeline  # noqa: F401
        return
    except ImportError:
        pass

    import boto3

    bucket = _resolve_input_bucket()
    if not bucket:
        raise ImportError("INPUT_BUCKET nao informado; nao foi possivel carregar libs/app.zip")

    obj = boto3.client("s3").get_object(Bucket=bucket, Key="libs/app.zip")
    lib_dir = tempfile.mkdtemp(prefix="glue_libs_")
    with zipfile.ZipFile(io.BytesIO(obj["Body"].read())) as archive:
        archive.extractall(lib_dir)
    sys.path.insert(0, lib_dir)


_load_bundle()
from train_pipeline import main

if __name__ == "__main__":
    main()
