import yake
from config import config

class KeywordExtractor:
    def __init__(self):
        kw_config = config['keywords']
        self.kw_extractor = yake.KeywordExtractor(
            lan=config['translation']['target_language'],
            n=kw_config['max_ngram_size'],
            dedupLim=kw_config['deduplication']['threshold'],
            dedupFunc=kw_config['deduplication']['function'],
            windowsSize=kw_config['window_size'],
            top=kw_config['num_keywords']
        )
        
        # Load category keywords from config
        self.CATEGORY_KEYWORDS = {}
        self.CATEGORY_WEIGHTS = {}
        
        for category, data in kw_config['categories'].items():
            self.CATEGORY_KEYWORDS[category] = data['terms']
            self.CATEGORY_WEIGHTS[category] = data.get('weight', 1.0)
        
        # Load scoring config
        self.EXACT_MATCH_SCORE = kw_config['scoring']['exact_match']
        self.PARTIAL_MATCH_SCORE = kw_config['scoring']['partial_match']
        
        # Load fallback config
        self.fallback_config = kw_config['fallback']
    
    def extract_keywords(self, text):
        try:
            # Extract keywords
            keywords = self.kw_extractor.extract_keywords(text)
            # Return only the keywords (not their scores)
            return [keyword[0] for keyword in keywords]
        except Exception as e:
            print(f"Error extracting keywords: {e}")
            return []
    
    @classmethod
    def create_default(cls):
        """Factory method for creating a default instance"""
        return cls()
    
    @classmethod
    def create_custom(cls, max_ngram_size=3, num_keywords=8):
        """Factory method for creating a custom instance"""
        return cls(max_ngram_size=max_ngram_size, num_keywords=num_keywords) 

    def categorize_content(self, keywords):
        """Determine the most relevant category based on keywords and content"""
        category_scores = {category: 0 for category in self.CATEGORY_KEYWORDS}
        
        # Convert keywords to lowercase for case-insensitive matching
        keywords = [kw.lower() for kw in keywords]
        
        # Score each category with weighted matching
        for keyword in keywords:
            for category, category_keywords in self.CATEGORY_KEYWORDS.items():
                # Exact match gets higher score
                if keyword in category_keywords:
                    category_scores[category] += self.EXACT_MATCH_SCORE
                # Partial match gets lower score
                elif any(cat_keyword in keyword for cat_keyword in category_keywords):
                    category_scores[category] += self.PARTIAL_MATCH_SCORE
                    
        # Get category with highest score
        max_score = max(category_scores.values())
        if max_score > 0:
            # If there's a tie, return the category with more exact matches
            max_categories = [
                category for category, score in category_scores.items() 
                if score == max_score
            ]
            if len(max_categories) > 1:
                # Count exact matches for tied categories
                exact_matches = {
                    category: sum(1 for kw in keywords if kw in self.CATEGORY_KEYWORDS[category])
                    for category in max_categories
                }
                return max(exact_matches.items(), key=lambda x: x[1])[0]
            return max_categories[0]
            
        # Default to 'Events' for time-related content
        if any(time_word in ' '.join(keywords).lower() 
               for time_word in ['week', 'weekend', 'upcoming', 'schedule', 'today', 'tomorrow']):
            return 'Events'
            
        return 'Other' 