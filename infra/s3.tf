# The wiki bucket (DESIGN §3, §4): versioning on, gives history/rollback
# without needing git. Seeded with CONVENTIONS.md/index.md/log.md from
# seed/ (DESIGN §14, §16) so the schema/conventions file exists from day one.

resource "aws_s3_bucket" "wiki" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_versioning" "wiki" {
  bucket = aws_s3_bucket.wiki.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "wiki" {
  bucket                  = aws_s3_bucket.wiki.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_object" "conventions" {
  bucket = aws_s3_bucket.wiki.id
  key    = "CONVENTIONS.md"
  source = "${path.module}/../seed/CONVENTIONS.md"
  etag   = filemd5("${path.module}/../seed/CONVENTIONS.md")

  lifecycle {
    ignore_changes = [source, etag] # remember/consolidate own this file after first apply
  }
}

resource "aws_s3_object" "index" {
  bucket = aws_s3_bucket.wiki.id
  key    = "index.md"
  source = "${path.module}/../seed/index.md"
  etag   = filemd5("${path.module}/../seed/index.md")

  lifecycle {
    ignore_changes = [source, etag] # remember owns this file after first apply
  }
}

resource "aws_s3_object" "log" {
  bucket = aws_s3_bucket.wiki.id
  key    = "log.md"
  source = "${path.module}/../seed/log.md"
  etag   = filemd5("${path.module}/../seed/log.md")

  lifecycle {
    ignore_changes = [source, etag] # remember/consolidate append to this file after first apply
  }
}
