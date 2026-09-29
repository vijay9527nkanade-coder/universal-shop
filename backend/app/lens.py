"""
app/lens.py
===========
CLIP-based image embeddings and FAISS index for visual product search.
"""

import logging
import requests
from io import BytesIO
import numpy as np
from PIL import Image

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product

logger = logging.getLogger(__name__)
router = APIRouter(tags=["lens"])

# Global references
_model = None
faiss = None
_index = None
_product_id_map = {}  # Maps FAISS integer ID -> DB Product ID

# Attempt to load ML dependencies
try:
    import faiss
    from sentence_transformers import SentenceTransformer
    
    # Note: Loading the model here takes a few seconds on startup and downloads it if missing.
    # We use clip-ViT-B-32 as it's standard and fast for visual search.
    _model = SentenceTransformer('clip-ViT-B-32')
    logger.info("CLIP model loaded successfully.")
except ImportError:
    logger.error("sentence-transformers or faiss is missing. Please install them to enable Lens.")


def generate_embedding(image_source) -> np.ndarray:
    """
    Generate a normalized CLIP embedding for an image.
    Supports either a URL string or raw bytes.
    """
    if _model is None or faiss is None:
        raise RuntimeError("CLIP model or FAISS is not available.")
        
    if isinstance(image_source, str) and image_source.startswith('http'):
        response = requests.get(image_source, timeout=10)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content)).convert('RGB')
    elif isinstance(image_source, bytes):
        img = Image.open(BytesIO(image_source)).convert('RGB')
    else:
        img = image_source.convert('RGB')
        
    # Encode generates a vector (typically 512-dim for ViT-B-32)
    embedding = _model.encode(img)
    
    # Normalize for cosine similarity using Inner Product
    faiss.normalize_L2(embedding.reshape(1, -1))
    return embedding.reshape(-1)


def rebuild_index(db: Session):
    """
    Fetches all products with images from the database, generates embeddings,
    and rebuilds the global FAISS index.
    """
    global _index, _product_id_map
    
    if _model is None or faiss is None:
        logger.error("Cannot rebuild FAISS index: missing dependencies.")
        return
        
    products = db.query(Product).filter(
        Product.image_url.isnot(None), 
        Product.image_url != ""
    ).all()
    
    if not products:
        logger.info("No products with images found to index.")
        return
        
    # clip-ViT-B-32 has an embedding dimension of 512
    dim = 512
    # IndexFlatIP uses Inner Product, which is equivalent to Cosine Similarity when vectors are L2 normalized
    new_index = faiss.IndexFlatIP(dim)
    new_id_map = {}
    
    embeddings = []
    
    logger.info(f"Rebuilding FAISS index for {len(products)} products...")
    
    for idx, product in enumerate(products):
        try:
            emb = generate_embedding(product.image_url)
            embeddings.append(emb)
            new_id_map[idx] = product.id
        except Exception as e:
            logger.warning(f"Failed to index image for product {product.id}: {e}")
            
    if embeddings:
        emb_matrix = np.vstack(embeddings).astype('float32')
        new_index.add(emb_matrix)
        
        # Atomically swap the active index
        _index = new_index
        _product_id_map = new_id_map
        logger.info(f"Successfully indexed {len(embeddings)} product images.")
    else:
        logger.warning("No embeddings were successfully generated.")


@router.post("/lens/rebuild-index")
def trigger_rebuild(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Manually triggers a rebuild of the FAISS index in the background.
    """
    background_tasks.add_task(rebuild_index, db)
    return {"message": "FAISS index rebuild started in the background."}


@router.post("/lens")
async def visual_search(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Upload an image to find the 5 nearest products via CLIP + FAISS cosine similarity.
    Returns results in the standard list format.
    """
    if _index is None or not _product_id_map:
        raise HTTPException(
            status_code=503, 
            detail="FAISS index is empty or building. Trigger /lens/rebuild-index first."
        )
        
    try:
        image_bytes = await file.read()
        query_emb = generate_embedding(image_bytes)
        query_emb = query_emb.reshape(1, -1).astype('float32')
        
        # Search for top 5
        top_k = 5
        distances, indices = _index.search(query_emb, top_k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx == -1:
                continue # Not enough results
                
            product_id = _product_id_map[idx]
            product = db.query(Product).filter(Product.id == product_id).first()
            
            if product:
                # Format exactly like the /search endpoint response
                p_dict = {
                    "id": product.id,
                    "platform": product.platform,
                    "product_url": product.product_url,
                    "name": product.name,
                    "category": product.category,
                    "price": float(product.price) if product.price else None,
                    "rating": float(product.rating) if product.rating else None,
                    "review_count": product.review_count,
                    "image_url": product.image_url,
                    "is_fallback": product.is_fallback,
                    "similarity_score": float(distances[0][i])
                }
                results.append(p_dict)
                
        return results
        
    except Exception as e:
        logger.exception("Visual search failed")
        raise HTTPException(status_code=500, detail=str(e))
