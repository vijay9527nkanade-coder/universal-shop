"""
app/sentiment.py
================
VADER sentiment analysis for product reviews.
"""

import logging
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.models import Review

logger = logging.getLogger(__name__)

# Try to initialize VADER analyzer safely
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _analyzer = SentimentIntensityAnalyzer()
except ImportError:
    try:
        import nltk
        # Ensure lexicon is downloaded if using nltk
        nltk.download('vader_lexicon', quiet=True)
        from nltk.sentiment.vader import SentimentIntensityAnalyzer
        _analyzer = SentimentIntensityAnalyzer()
    except ImportError:
        logger.error(
            "Neither `vaderSentiment` nor `nltk` is installed. "
            "Please run `pip install vaderSentiment` to enable sentiment scoring."
        )
        _analyzer = None


def get_vader_score(text: str) -> float:
    """
    Score text using VADER and return the compound score [-1.0, 1.0].
    Returns 0.0 if VADER is unavailable or text is empty.
    """
    if not _analyzer or not text or not text.strip():
        return 0.0
    
    # 'compound' score ranges from -1 (most extreme negative) to +1 (most extreme positive)
    scores = _analyzer.polarity_scores(text)
    return scores['compound']


def score_unprocessed_reviews(db: Session) -> int:
    """
    Find all reviews in the database that haven't been scored yet (sentiment_score is NULL),
    score them using VADER, and save the results back to the database.
    
    Returns the number of reviews processed.
    """
    unprocessed = db.query(Review).filter(Review.sentiment_score.is_(None)).all()
    
    if not unprocessed:
        return 0
        
    for review in unprocessed:
        review.sentiment_score = get_vader_score(review.review_text)
            
    db.commit()
    logger.info("Processed and scored %d previously unscored reviews.", len(unprocessed))
    return len(unprocessed)


def get_product_average_sentiment(db: Session, product_id: int) -> float:
    """
    Computes and returns the average sentiment score for a given product_id.
    Returns 0.0 if there are no scored reviews for this product.
    """
    result = db.query(func.avg(Review.sentiment_score)).filter(
        Review.product_id == product_id,
        Review.sentiment_score.isnot(None)
    ).scalar()
    
    return float(result) if result is not None else 0.0


def score_product_reviews(db: Session, product_id: int) -> float:
    """
    Utility function to score all unscored reviews for a single product,
    save the updates, and immediately return the new average sentiment score.
    """
    unprocessed = db.query(Review).filter(
        Review.product_id == product_id,
        Review.sentiment_score.is_(None)
    ).all()
    
    if unprocessed:
        for review in unprocessed:
            review.sentiment_score = get_vader_score(review.review_text)
        db.commit()
        
    return get_product_average_sentiment(db, product_id)
