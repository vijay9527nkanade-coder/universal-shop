"""
app/ranking.py
==============
Ranking engine to score and sort products based on price, rating, reviews, and sentiment.
Uses min-max scaling and configurable weights.
"""

from typing import List, Dict, Any

def rank_products(products: List[Dict[str, Any]], weights: dict = None) -> List[Dict[str, Any]]:
    """
    Ranks a list of product dictionaries based on normalized metrics.
    Returns the top 3 products, prioritizing platform diversity.
    """
    if not products:
        return []
        
    if weights is None:
        weights = {
            "rating": 0.3,
            "sentiment": 0.3,
            "review_count": 0.2,
            "price": 0.2
        }
        
    # Extract non-None values to find global min/max for scaling
    prices = [float(p["price"]) for p in products if p.get("price") is not None]
    ratings = [float(p["rating"]) for p in products if p.get("rating") is not None]
    review_counts = [float(p["review_count"]) for p in products if p.get("review_count") is not None]
    sentiments = [float(p.get("sentiment_score", 0.0)) for p in products]
    
    def get_min_max(vals: List[float], default_min: float = 0.0, default_max: float = 1.0) -> tuple[float, float]:
        if not vals:
            return default_min, default_max
        v_min, v_max = min(vals), max(vals)
        if v_min == v_max:
            # Prevent division by zero if all products have the exact same value
            return v_min, v_max + 1e-9 
        return v_min, v_max
        
    min_price, max_price = get_min_max(prices)
    min_rating, max_rating = get_min_max(ratings, 0.0, 5.0)
    min_reviews, max_reviews = get_min_max(review_counts, 0.0, 1.0)
    min_sent, max_sent = get_min_max(sentiments, -1.0, 1.0)
    
    scored_products = []
    
    for p in products:
        # 1. Price Score (Lower price is better)
        price = p.get("price")
        if price is not None:
            norm_price = (float(price) - min_price) / (max_price - min_price)
            price_score = 1.0 - norm_price
        else:
            price_score = 0.5  # Neutral fallback
            
        # 2. Rating Score (Higher is better)
        rating = p.get("rating")
        if rating is not None:
            rating_score = (float(rating) - min_rating) / (max_rating - min_rating)
        else:
            rating_score = 0.5
            
        # 3. Review Count Score (Higher is better)
        reviews = p.get("review_count")
        if reviews is not None:
            review_score = (float(reviews) - min_reviews) / (max_reviews - min_reviews)
        else:
            review_score = 0.0
            
        # 4. Sentiment Score (Higher is better)
        sentiment = p.get("sentiment_score", 0.0)
        sentiment_score = (float(sentiment) - min_sent) / (max_sent - min_sent)
        
        # Calculate final weighted total
        total_score = (
            price_score * weights["price"] +
            rating_score * weights["rating"] +
            review_score * weights["review_count"] +
            sentiment_score * weights["sentiment"]
        )
        
        # Copy dictionary to avoid mutating original list references and append score
        scored_p = dict(p)
        scored_p["rank_score"] = total_score
        scored_products.append(scored_p)
        
    # Sort strictly by the calculated rank_score descending
    scored_products.sort(key=lambda x: x["rank_score"], reverse=True)
    
    # Selection logic: Top 3, prioritizing 1 per platform
    selected = []
    seen_platforms = set()
    
    # Pass 1: Grab the highest scoring product from unique platforms
    for p in scored_products:
        if p["platform"] not in seen_platforms:
            selected.append(p)
            seen_platforms.add(p["platform"])
            if len(selected) == 3:
                break
                
    # Pass 2: If we have less than 3 (e.g. only 2 platforms succeeded), fill the rest with the next best products
    if len(selected) < 3:
        selected_urls = {s["product_url"] for s in selected}
        for p in scored_products:
            if p["product_url"] not in selected_urls:
                selected.append(p)
                selected_urls.add(p["product_url"])
                if len(selected) == 3:
                    break
                    
    return selected
