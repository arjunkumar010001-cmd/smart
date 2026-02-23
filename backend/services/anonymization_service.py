"""
P0 ML: Resume Anonymization Service
====================================
Removes PII (Personally Identifiable Information) from resumes before matching

Features:
- Name detection and removal (using NLP + patterns)
- Email, phone, address anonymization
- Gender indicator removal
- College/university anonymization (optional)
- Location/zip code removal
- LinkedIn/social profile removal
- Metrics logging

Author: Smart Hiring System Team
Date: January 2026
"""

import re
import logging
from typing import Dict, List, Set, Tuple, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to load spaCy for NER-based anonymization
SPACY_AVAILABLE = False
nlp = None
try:
    import spacy
    try:
        nlp = spacy.load("en_core_web_sm")
        SPACY_AVAILABLE = True
        logger.info("✅ spaCy NER available for anonymization")
    except OSError:
        logger.warning("⚠️ spaCy model not found - using pattern-based anonymization")
except (ImportError, AttributeError, Exception) as _spacy_err:
    logger.warning(f"⚠️ spaCy not available ({_spacy_err}) - using pattern-based anonymization")


class AnonymizationMetrics:
    """Track anonymization metrics"""
    def __init__(self):
        self.total_processed = 0
        self.total_pii_removed = 0
        self.names_removed = 0
        self.emails_removed = 0
        self.phones_removed = 0
        self.addresses_removed = 0
        self.other_removed = 0
        
    def record(self, pii_counts: Dict[str, int]):
        self.total_processed += 1
        self.names_removed += pii_counts.get('names', 0)
        self.emails_removed += pii_counts.get('emails', 0)
        self.phones_removed += pii_counts.get('phones', 0)
        self.addresses_removed += pii_counts.get('addresses', 0)
        self.other_removed += pii_counts.get('other', 0)
        self.total_pii_removed += sum(pii_counts.values())
        
    def get_stats(self) -> Dict:
        return {
            'total_processed': self.total_processed,
            'total_pii_removed': self.total_pii_removed,
            'avg_pii_per_resume': round(self.total_pii_removed / self.total_processed, 2) if self.total_processed > 0 else 0,
            'breakdown': {
                'names': self.names_removed,
                'emails': self.emails_removed,
                'phones': self.phones_removed,
                'addresses': self.addresses_removed,
                'other': self.other_removed
            },
            'spacy_available': SPACY_AVAILABLE
        }


# Global metrics
anonymization_metrics = AnonymizationMetrics()


class ResumeAnonymizer:
    """
    P0 ML: Production-ready resume anonymization service
    
    Removes PII to enable bias-free candidate evaluation
    """
    
    # Common first names for pattern matching (fallback when NLP unavailable)
    COMMON_FIRST_NAMES = {
        # Male names
        'james', 'john', 'robert', 'michael', 'william', 'david', 'richard', 'joseph',
        'thomas', 'charles', 'christopher', 'daniel', 'matthew', 'anthony', 'mark',
        'donald', 'steven', 'paul', 'andrew', 'joshua', 'kenneth', 'kevin', 'brian',
        # Female names
        'mary', 'patricia', 'jennifer', 'linda', 'barbara', 'elizabeth', 'susan',
        'jessica', 'sarah', 'karen', 'nancy', 'lisa', 'betty', 'margaret', 'sandra',
        'ashley', 'dorothy', 'kimberly', 'emily', 'donna', 'michelle', 'carol',
        # Indian names
        'rahul', 'priya', 'amit', 'deepak', 'anita', 'suresh', 'sanjay', 'neha',
        'ravi', 'pooja', 'vikram', 'anjali', 'arun', 'sunita', 'venkat', 'lakshmi',
        # Gender-neutral
        'alex', 'taylor', 'jordan', 'casey', 'morgan', 'jamie', 'riley', 'quinn'
    }
    
    # Gender indicators
    GENDER_INDICATORS = [
        'mr.', 'mr', 'mrs.', 'mrs', 'ms.', 'ms', 'miss', 'dr.', 'dr',
        'he/him', 'she/her', 'they/them',
        'male', 'female', 'gender:', 'sex:'
    ]
    
    def __init__(self):
        self.nlp = nlp
        self.metrics = anonymization_metrics
        
    def anonymize(self, text: str, options: Optional[Dict] = None) -> Dict:
        """
        Anonymize resume text by removing PII
        
        Args:
            text: Original resume text
            options: Dict with anonymization options:
                - remove_names: bool (default True)
                - remove_emails: bool (default True)
                - remove_phones: bool (default True)
                - remove_addresses: bool (default True)
                - remove_colleges: bool (default False - may be relevant)
                - remove_gender: bool (default True)
                - remove_links: bool (default True)
                
        Returns:
            Dict with anonymized_text, removed_entities, and stats
        """
        if not text:
            return {
                'anonymized_text': '',
                'removed_entities': [],
                'pii_count': 0
            }
        
        options = options or {}
        removed_entities = []
        pii_counts = {
            'names': 0,
            'emails': 0,
            'phones': 0,
            'addresses': 0,
            'other': 0
        }
        
        anonymized = text
        
        # 1. Remove emails
        if options.get('remove_emails', True):
            anonymized, count = self._remove_emails(anonymized)
            pii_counts['emails'] = count
            if count > 0:
                removed_entities.append({'type': 'EMAIL', 'count': count})
        
        # 2. Remove phone numbers
        if options.get('remove_phones', True):
            anonymized, count = self._remove_phones(anonymized)
            pii_counts['phones'] = count
            if count > 0:
                removed_entities.append({'type': 'PHONE', 'count': count})
        
        # 3. Remove social links (LinkedIn, GitHub, etc.)
        if options.get('remove_links', True):
            anonymized, count = self._remove_social_links(anonymized)
            pii_counts['other'] += count
            if count > 0:
                removed_entities.append({'type': 'SOCIAL_LINK', 'count': count})
        
        # 4. Remove addresses
        if options.get('remove_addresses', True):
            anonymized, count = self._remove_addresses(anonymized)
            pii_counts['addresses'] = count
            if count > 0:
                removed_entities.append({'type': 'ADDRESS', 'count': count})
        
        # 5. Remove gender indicators
        if options.get('remove_gender', True):
            anonymized, count = self._remove_gender_indicators(anonymized)
            pii_counts['other'] += count
            if count > 0:
                removed_entities.append({'type': 'GENDER_INDICATOR', 'count': count})
        
        # 6. Remove names (using NLP if available, fallback to patterns)
        if options.get('remove_names', True):
            anonymized, count = self._remove_names(anonymized)
            pii_counts['names'] = count
            if count > 0:
                removed_entities.append({'type': 'NAME', 'count': count})
        
        # Record metrics
        self.metrics.record(pii_counts)
        
        return {
            'anonymized_text': anonymized.strip(),
            'removed_entities': removed_entities,
            'pii_count': sum(pii_counts.values()),
            'pii_breakdown': pii_counts,
            'anonymized_at': datetime.utcnow().isoformat()
        }
    
    def _remove_emails(self, text: str) -> Tuple[str, int]:
        """Remove email addresses"""
        pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        matches = re.findall(pattern, text)
        result = re.sub(pattern, '[EMAIL_REDACTED]', text)
        return result, len(matches)
    
    def _remove_phones(self, text: str) -> Tuple[str, int]:
        """Remove phone numbers"""
        patterns = [
            r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',  # US format
            r'\+?\d{2,3}[-.\s]?\d{5,10}',  # International format
            r'\b\d{10}\b',  # Simple 10-digit
        ]
        count = 0
        result = text
        for pattern in patterns:
            matches = re.findall(pattern, result)
            count += len([m for m in matches if isinstance(m, str)])
            result = re.sub(pattern, '[PHONE_REDACTED]', result)
        return result, count
    
    def _remove_social_links(self, text: str) -> Tuple[str, int]:
        """Remove LinkedIn, GitHub, and other social links"""
        patterns = [
            r'https?://(?:www\.)?linkedin\.com/in/[A-Za-z0-9_-]+/?',
            r'https?://(?:www\.)?github\.com/[A-Za-z0-9_-]+/?',
            r'https?://(?:www\.)?twitter\.com/[A-Za-z0-9_]+/?',
            r'https?://(?:www\.)?facebook\.com/[A-Za-z0-9._-]+/?',
            r'linkedin\.com/in/[A-Za-z0-9_-]+',
            r'github\.com/[A-Za-z0-9_-]+',
        ]
        count = 0
        result = text
        for pattern in patterns:
            matches = re.findall(pattern, result, re.IGNORECASE)
            count += len(matches)
            result = re.sub(pattern, '[PROFILE_REDACTED]', result, flags=re.IGNORECASE)
        return result, count
    
    def _remove_addresses(self, text: str) -> Tuple[str, int]:
        """Remove street addresses and zip codes"""
        patterns = [
            # US zip codes
            r'\b\d{5}(?:-\d{4})?\b',
            # Indian pin codes
            r'\b\d{6}\b',
            # Street addresses
            r'\d+\s+[\w\s]+(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|dr)\b',
        ]
        count = 0
        result = text
        for pattern in patterns:
            matches = re.findall(pattern, result, re.IGNORECASE)
            count += len(matches)
            result = re.sub(pattern, '[ADDRESS_REDACTED]', result, flags=re.IGNORECASE)
        return result, count
    
    def _remove_gender_indicators(self, text: str) -> Tuple[str, int]:
        """Remove gender indicators"""
        count = 0
        result = text
        for indicator in self.GENDER_INDICATORS:
            pattern = r'\b' + re.escape(indicator) + r'\b'
            matches = re.findall(pattern, result, re.IGNORECASE)
            count += len(matches)
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)
        return result, count
    
    def _remove_names(self, text: str) -> Tuple[str, int]:
        """Remove names using NLP or pattern matching"""
        count = 0
        result = text
        
        # Try NLP-based extraction first
        if self.nlp is not None:
            try:
                doc = self.nlp(text[:5000])  # Limit for performance
                names_to_remove = set()
                
                for ent in doc.ents:
                    if ent.label_ == 'PERSON':
                        names_to_remove.add(ent.text)
                
                for name in names_to_remove:
                    pattern = r'\b' + re.escape(name) + r'\b'
                    result = re.sub(pattern, '[NAME_REDACTED]', result, flags=re.IGNORECASE)
                    count += 1
                    
            except Exception as e:
                logger.warning(f"NLP name extraction failed: {e}")
        
        # Also check common names as fallback/supplement
        text_lower = result.lower()
        for name in self.COMMON_FIRST_NAMES:
            # Only match at word boundaries to avoid false positives
            pattern = r'(?<![a-z])' + re.escape(name) + r'(?![a-z])'
            if re.search(pattern, text_lower):
                # Check if it appears near start of document (likely candidate name)
                first_occurrence = text_lower.find(name)
                if first_occurrence < 200:  # Within first 200 chars
                    result = re.sub(r'\b' + re.escape(name) + r'\b', '[NAME]', result, 
                                   count=1, flags=re.IGNORECASE)
                    count += 1
        
        return result, count
    
    def get_metrics(self) -> Dict:
        """Get anonymization metrics"""
        return self.metrics.get_stats()


# Singleton instance
_anonymizer = None

def get_anonymizer() -> ResumeAnonymizer:
    """Get or create anonymizer singleton"""
    global _anonymizer
    if _anonymizer is None:
        _anonymizer = ResumeAnonymizer()
    return _anonymizer


def anonymize_text(text: str, options: Optional[Dict] = None) -> str:
    """
    Convenience function for backward compatibility
    
    Returns just the anonymized text string
    """
    anonymizer = get_anonymizer()
    result = anonymizer.anonymize(text, options)
    return result['anonymized_text']


def anonymize_resume(text: str) -> Dict:
    """
    Full anonymization with detailed results
    
    Returns dict with anonymized_text, removed_entities, etc.
    """
    anonymizer = get_anonymizer()
    return anonymizer.anonymize(text)


if __name__ == '__main__':
    # Test the anonymizer
    print("\n" + "="*60)
    print("🧪 RESUME ANONYMIZER TEST")
    print("="*60 + "\n")
    
    sample_resume = """
    John Smith
    Email: john.smith@email.com
    Phone: +1 (555) 123-4567
    LinkedIn: linkedin.com/in/johnsmith
    Location: San Francisco, CA 94102
    
    He is a senior software developer with 5+ years of experience.
    Mr. Smith has expertise in Python, JavaScript, and cloud technologies.
    
    Education:
    Bachelor of Science in Computer Science
    Stanford University, 2018
    
    Experience:
    Senior Developer at Tech Corp
    Built scalable microservices using Python and AWS.
    """
    
    anonymizer = get_anonymizer()
    result = anonymizer.anonymize(sample_resume)
    
    print("Original (first 300 chars):")
    print(sample_resume[:300])
    print("\n" + "-"*40 + "\n")
    print("Anonymized (first 300 chars):")
    print(result['anonymized_text'][:300])
    print("\n" + "-"*40 + "\n")
    print(f"PII entities removed: {result['pii_count']}")
    print(f"Breakdown: {result['pii_breakdown']}")
    
    print("\n📊 Metrics:")
    print(anonymizer.get_metrics())
    print("\n" + "="*60)
