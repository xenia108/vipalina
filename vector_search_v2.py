"""
Vector Search v2 - Enhanced version with better performance and additional features
"""

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re
import json
from typing import List, Tuple, Dict, Optional
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VectorCourseSearchV2:
    def __init__(self, course_data: List[Dict] = None):
        """
        Initialize the VectorCourseSearchV2 with course data
        
        Args:
            course_data: List of dictionaries containing course information
        """
        self.course_data = course_data or []
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words='english',
            ngram_range=(1, 2),
            max_features=10000
        )
        self.course_vectors = None
        self.course_titles = []
        self._prepare_vectors()
    
    def _prepare_vectors(self):
        """Prepare TF-IDF vectors for all courses"""
        if not self.course_data:
            logger.warning("No course data provided")
            return
        
        # Extract text content from courses
        course_texts = []
        self.course_titles = []
        
        for course in self.course_data:
            # Combine relevant fields for vectorization
            title = course.get('title', '')
            description = course.get('description', '')
            content = course.get('content', '')
            
            # Create a comprehensive text representation
            combined_text = f"{title} {description} {content}"
            course_texts.append(combined_text)
            self.course_titles.append(title)
        
        # Create TF-IDF vectors
        try:
            self.course_vectors = self.vectorizer.fit_transform(course_texts)
            logger.info(f"Prepared vectors for {len(self.course_data)} courses")
        except Exception as e:
            logger.error(f"Error preparing vectors: {e}")
    
    def search(self, query: str, top_k: int = 5) -> List[Tuple[int, float, Dict]]:
        """
        Search for courses similar to the query
        
        Args:
            query: Search query string
            top_k: Number of top results to return
            
        Returns:
            List of tuples (index, similarity_score, course_data)
        """
        if self.course_vectors is None:
            logger.warning("No vectors prepared for search")
            return []
        
        try:
            # Transform query to vector space
            query_vector = self.vectorizer.transform([query])
            
            # Calculate cosine similarities
            similarities = cosine_similarity(query_vector, self.course_vectors).flatten()
            
            # Get top-k most similar courses
            top_indices = similarities.argsort()[-top_k:][::-1]
            
            # Prepare results
            results = []
            for idx in top_indices:
                if similarities[idx] > 0:  # Only include positive similarities
                    results.append((idx, similarities[idx], self.course_data[idx]))
            
            return results
        except Exception as e:
            logger.error(f"Error during search: {e}")
            return []
    
    def add_course(self, course: Dict):
        """Add a new course to the search index"""
        self.course_data.append(course)
        self._prepare_vectors()  # Rebuild vectors with new data
    
    def remove_course(self, index: int):
        """Remove a course from the search index by index"""
        if 0 <= index < len(self.course_data):
            self.course_data.pop(index)
            self._prepare_vectors()  # Rebuild vectors without removed data
    
    def update_course(self, index: int, course: Dict):
        """Update a course in the search index"""
        if 0 <= index < len(self.course_data):
            self.course_data[index] = course
            self._prepare_vectors()  # Rebuild vectors with updated data
    
    def get_course_count(self) -> int:
        """Get the number of courses in the search index"""
        return len(self.course_data)
    
    def get_course_by_index(self, index: int) -> Optional[Dict]:
        """Get a course by its index"""
        if 0 <= index < len(self.course_data):
            return self.course_data[index]
        return None
    
    def search_by_keywords(self, keywords: List[str], top_k: int = 5) -> List[Tuple[int, float, Dict]]:
        """
        Search for courses containing specific keywords
        
        Args:
            keywords: List of keywords to search for
            top_k: Number of top results to return
            
        Returns:
            List of tuples (index, similarity_score, course_data)
        """
        if not keywords or not self.course_data:
            return []
        
        # Create a query from keywords
        query = ' '.join(keywords)
        return self.search(query, top_k)
    
    def fuzzy_search(self, query: str, threshold: float = 0.1, top_k: int = 5) -> List[Tuple[int, float, Dict]]:
        """
        Perform fuzzy search with a similarity threshold
        
        Args:
            query: Search query string
            threshold: Minimum similarity score (0-1)
            top_k: Number of top results to return
            
        Returns:
            List of tuples (index, similarity_score, course_data)
        """
        results = self.search(query, len(self.course_data))  # Get all results
        filtered_results = [r for r in results if r[1] >= threshold]
        return filtered_results[:top_k]

def load_course_data_from_file(file_path: str) -> List[Dict]:
    """
    Load course data from a JSON file
    
    Args:
        file_path: Path to the JSON file containing course data
        
    Returns:
        List of course dictionaries
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"Error loading course data from {file_path}: {e}")
        return []

def save_course_data_to_file(course_data: List[Dict], file_path: str):
    """
    Save course data to a JSON file
    
    Args:
        course_data: List of course dictionaries
        file_path: Path to save the JSON file
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(course_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Course data saved to {file_path}")
    except Exception as e:
        logger.error(f"Error saving course data to {file_path}: {e}")

# Example usage
if __name__ == "__main__":
    # Example course data
    sample_courses = [
        {
            "title": "Python Programming Basics",
            "description": "Learn the fundamentals of Python programming language",
            "content": "Variables, loops, functions, classes, modules"
        },
        {
            "title": "Advanced Machine Learning",
            "description": "Deep dive into machine learning algorithms and techniques",
            "content": "Neural networks, deep learning, reinforcement learning"
        },
        {
            "title": "Web Development with React",
            "description": "Build modern web applications with React framework",
            "content": "Components, state management, hooks, routing"
        }
    ]
    
    # Initialize vector search
    searcher = VectorCourseSearchV2(sample_courses)
    
    # Perform a search
    results = searcher.search("python programming")
    print("Search results:")
    for idx, score, course in results:
        print(f"  {score:.3f}: {course['title']}")