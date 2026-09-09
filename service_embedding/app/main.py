"""
main.py — Entry point for the CLIP image-similarity Fargate task.

Pipeline
--------
1. Load reference embeddings matrix from DB (train_embeddings table).
2. Load location name mapping from DB (locations_info table).
3. List PNG images from s3://INPUT_BUCKET/INPUT_PREFIX/.
4. Load CLIP model once.
5. For every query image:
     a. Download from S3.
     b. Embed with CLIP.
     c. Find closest reference row via cosine similarity (dot product of
        L2-normalised vectors).
     d. Collect result.
6. Write summary CSV to s3://OUTPUT_BUCKET/OUTPUT_PREFIX/.
7. Exit 0 on success, 1 on failure.
"""

import logging
import os
import sys

import numpy as np

from app.db       import fetch_reference_embeddings, fetch_location_names
from app.embedder import embed_image
from app.s3_io    import list_input_images, download_image, upload_results_csv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def run() -> None:
    logger.info("=== CLIP image-similarity job starting ===")

    # 1. Load reference embeddings from DB
    logger.info("Step 1/5 — loading reference embeddings from DB …")
    ref_matrix, ref_meta = fetch_reference_embeddings()
    logger.info("Reference matrix shape: %s", ref_matrix.shape)

    # 2. Load location names from DB
    logger.info("Step 2/5 — loading location names from DB …")
    location_names = fetch_location_names()

    # 3. List query images in S3
    logger.info("Step 3/5 — listing query images in S3 …")
    image_keys = list_input_images()
    if not image_keys:
        raise RuntimeError("No PNG images found in the input S3 prefix. Nothing to do.")

    # 4 & 5. Embed each query image and find its best match
    logger.info("Step 4/5 — embedding %d images and matching …", len(image_keys))
    results = []

    for key in image_keys:
        filename = os.path.basename(key)
        logger.info("  Processing: %s", filename)

        # Download + embed
        pil_image = download_image(key)
        query_vec = embed_image(pil_image)          # shape: (D,), L2-normalised

        # Cosine similarity = dot product (both sides L2-normalised)
        similarities = ref_matrix @ query_vec       # shape: (N,)
        best_idx     = int(np.argmax(similarities))
        best_sim     = float(similarities[best_idx])

        best_row       = ref_meta[best_idx]
        point_id       = best_row["id_point"]
        location_name  = location_names.get(point_id, "Unknown")
        ref_image_name = best_row["image_name"]

        logger.info(
            "    → %s | similarity=%.4f | location=%s (point_id=%s)",
            filename, best_sim, location_name, point_id,
        )

        results.append({
            "query_image":       filename,
            "predicted_point_id": point_id,
            "predicted_location": location_name,
            "similarity":         f"{best_sim * 100:.2f}%",
            "matched_ref_image":  ref_image_name,
        })

    # 6. Upload summary CSV
    logger.info("Step 5/5 — uploading results CSV …")
    output_uri = upload_results_csv(results)

    logger.info("=== Job finished successfully. Results → %s ===", output_uri)

    # Print summary table to CloudWatch logs
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(
        f"{'Query Image':<35} {'Location':<20} {'Similarity':>10}"
    )
    print("-" * 70)
    for r in results:
        print(
            f"{r['query_image']:<35} {r['predicted_location']:<20} {r['similarity']:>10}"
        )
    print("=" * 70)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        logger.exception("Job failed: %s", exc)
        sys.exit(1)
