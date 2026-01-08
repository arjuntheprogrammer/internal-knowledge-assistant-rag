class SafetyService:
    FORBIDDEN_TERMS = ['internal-confidential', 'secret-key']

    @classmethod
    def is_safe(cls, text):
        """
        Check if text contains any forbidden terms.
        Returns (is_safe, reason)
        """
        if not text:
            return True, None

        lower_text = text.lower()
        for term in cls.FORBIDDEN_TERMS:
            if term in lower_text:
                return False, f"Content contains restricted term: {term}"

        return True, None

    @classmethod
    def redact(cls, text):
        """
        Simple PII redaction (mock).
        """
        # Placeholder for actual PII redaction logic (e.g. email regex)
        return text
