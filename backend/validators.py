"""
Input validation utilities for the Garmin Training Dashboard.
Provides comprehensive validation for user inputs, API parameters, and data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union

from observability import ErrorCategory, ServiceError


# Email validation pattern (RFC 5322 simplified)
EMAIL_PATTERN = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)

# Date format patterns
ISO_DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')

# Dangerous patterns for injection attacks
SQL_INJECTION_PATTERNS = [
    r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE)\b)",
    r"(--|;|'|\")",
    r"(\b(OR|AND)\b\s+\d+\s*=\s*\d+)",
    r"(UNION\s+SELECT)",
    r"(\/\*|\*\/)",
]

XSS_PATTERNS = [
    r"<script[^>]*>",
    r"javascript:",
    r"on\w+\s*=",
    r"<iframe[^>]*>",
    r"<object[^>]*>",
    r"<embed[^>]*>",
]


@dataclass
class ValidationResult:
    """Result of a validation check."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    
    def raise_if_invalid(self) -> None:
        """Raise ServiceError if validation failed."""
        if not self.is_valid:
            raise ServiceError(
                "; ".join(self.errors),
                status_code=400,
                category=ErrorCategory.VALIDATION,
                event="validation.failed",
                context={"errors": self.errors, "warnings": self.warnings},
            )


class InputValidator:
    """Comprehensive input validator."""
    
    @staticmethod
    def validate_email(email: Any) -> ValidationResult:
        """Validate email format."""
        errors = []
        warnings = []
        
        if not email:
            errors.append("Email is required")
            return ValidationResult(False, errors, warnings)
        
        if not isinstance(email, str):
            errors.append("Email must be a string")
            return ValidationResult(False, errors, warnings)
        
        email = email.strip().lower()
        
        if len(email) > 254:
            errors.append("Email is too long (max 254 characters)")
        
        if not EMAIL_PATTERN.match(email):
            errors.append("Invalid email format")
        
        # Check for common typos
        common_typos = {
            "gmial.com": "gmail.com",
            "gmal.com": "gmail.com",
            "gamil.com": "gmail.com",
            "hotmail.co": "hotmail.com",
            "yahoo.co": "yahoo.com",
        }
        
        domain = email.split("@")[-1] if "@" in email else ""
        if domain in common_typos:
            warnings.append(f"Did you mean {email.replace(domain, common_typos[domain])}?")
        
        return ValidationResult(len(errors) == 0, errors, warnings)
    
    @staticmethod
    def validate_password(password: Any) -> ValidationResult:
        """Validate password strength."""
        errors = []
        warnings = []
        
        if not password:
            errors.append("Password is required")
            return ValidationResult(False, errors, warnings)
        
        if not isinstance(password, str):
            errors.append("Password must be a string")
            return ValidationResult(False, errors, warnings)
        
        if len(password) < 8:
            errors.append("Password must be at least 8 characters")
        
        if len(password) > 128:
            errors.append("Password is too long (max 128 characters)")
        
        # Check for weak passwords
        weak_passwords = {
            "password", "12345678", "qwerty123", "admin123",
            "letmein123", "welcome123", "monkey123", "1234567890",
        }
        
        if password.lower() in weak_passwords:
            errors.append("Password is too common")
        
        # Check for complexity (optional warnings)
        if not re.search(r'[A-Z]', password):
            warnings.append("Consider adding uppercase letters for stronger security")
        
        if not re.search(r'[a-z]', password):
            warnings.append("Consider adding lowercase letters")
        
        if not re.search(r'[0-9]', password):
            warnings.append("Consider adding numbers")
        
        if not re.search(r'[^A-Za-z0-9]', password):
            warnings.append("Consider adding special characters")
        
        return ValidationResult(len(errors) == 0, errors, warnings)
    
    @staticmethod
    def validate_iso_date(date_str: Any, field_name: str = "date") -> ValidationResult:
        """Validate ISO date format (YYYY-MM-DD)."""
        errors = []
        warnings = []
        
        if not date_str:
            errors.append(f"{field_name} is required")
            return ValidationResult(False, errors, warnings)
        
        if not isinstance(date_str, str):
            errors.append(f"{field_name} must be a string")
            return ValidationResult(False, errors, warnings)
        
        date_str = date_str.strip()
        
        if not ISO_DATE_PATTERN.match(date_str):
            errors.append(f"{field_name} must be in YYYY-MM-DD format")
            return ValidationResult(False, errors, warnings)
        
        try:
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            # Check if date is reasonable
            today = date.today()
            min_date = date(2020, 1, 1)  # Reasonable minimum
            max_date = date(today.year + 1, 12, 31)  # Allow up to next year
            
            if parsed_date < min_date:
                errors.append(f"{field_name} is too far in the past")
            
            if parsed_date > max_date:
                errors.append(f"{field_name} is too far in the future")
            
        except ValueError:
            errors.append(f"{field_name} is not a valid date")
        
        return ValidationResult(len(errors) == 0, errors, warnings)
    
    @staticmethod
    def validate_integer(
        value: Any,
        field_name: str,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
        required: bool = True,
    ) -> ValidationResult:
        """Validate integer value."""
        errors = []
        warnings = []
        
        if value is None:
            if required:
                errors.append(f"{field_name} is required")
            return ValidationResult(not required, errors, warnings)
        
        # Try to convert to int
        try:
            if isinstance(value, bool):
                errors.append(f"{field_name} must be a number, not a boolean")
                return ValidationResult(False, errors, warnings)
            
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    if required:
                        errors.append(f"{field_name} is required")
                    return ValidationResult(not required, errors, warnings)
            
            int_value = int(value)
            
        except (ValueError, TypeError):
            errors.append(f"{field_name} must be a valid integer")
            return ValidationResult(False, errors, warnings)
        
        # Check bounds
        if min_value is not None and int_value < min_value:
            errors.append(f"{field_name} must be at least {min_value}")
        
        if max_value is not None and int_value > max_value:
            errors.append(f"{field_name} must be at most {max_value}")
        
        return ValidationResult(len(errors) == 0, errors, warnings)
    
    @staticmethod
    def validate_string(
        value: Any,
        field_name: str,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        required: bool = True,
        allow_empty: bool = False,
    ) -> ValidationResult:
        """Validate string value."""
        errors = []
        warnings = []
        
        if value is None:
            if required:
                errors.append(f"{field_name} is required")
            return ValidationResult(not required, errors, warnings)
        
        if not isinstance(value, str):
            errors.append(f"{field_name} must be a string")
            return ValidationResult(False, errors, warnings)
        
        value = value.strip()
        
        if not value and not allow_empty:
            if required:
                errors.append(f"{field_name} is required")
            return ValidationResult(not required, errors, warnings)
        
        # Check length
        if min_length is not None and len(value) < min_length:
            errors.append(f"{field_name} must be at least {min_length} characters")
        
        if max_length is not None and len(value) > max_length:
            errors.append(f"{field_name} must be at most {max_length} characters")
        
        return ValidationResult(len(errors) == 0, errors, warnings)
    
    @staticmethod
    def sanitize_string(value: str, max_length: int = 1000) -> str:
        """Sanitize string input to prevent injection attacks."""
        if not isinstance(value, str):
            return ""
        
        # Strip whitespace
        value = value.strip()
        
        # Truncate if too long
        if len(value) > max_length:
            value = value[:max_length]
        
        # Remove null bytes
        value = value.replace('\x00', '')
        
        # Remove control characters (except newlines and tabs)
        value = ''.join(
            char for char in value
            if char == '\n' or char == '\t' or not unicodedata.category(char).startswith('C')
        )
        
        return value
    
    @staticmethod
    def check_sql_injection(value: str) -> ValidationResult:
        """Check for potential SQL injection patterns."""
        errors = []
        warnings = []
        
        if not isinstance(value, str):
            return ValidationResult(True, errors, warnings)
        
        value_lower = value.lower()
        
        for pattern in SQL_INJECTION_PATTERNS:
            if re.search(pattern, value_lower, re.IGNORECASE):
                errors.append("Input contains potentially dangerous patterns")
                break
        
        return ValidationResult(len(errors) == 0, errors, warnings)
    
    @staticmethod
    def check_xss(value: str) -> ValidationResult:
        """Check for potential XSS patterns."""
        errors = []
        warnings = []
        
        if not isinstance(value, str):
            return ValidationResult(True, errors, warnings)
        
        for pattern in XSS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                errors.append("Input contains potentially dangerous HTML/JavaScript patterns")
                break
        
        return ValidationResult(len(errors) == 0, errors, warnings)


class GarminCredentialsValidator:
    """Specialized validator for Garmin credentials."""
    
    @staticmethod
    def validate(email: Any, password: Any) -> tuple[str, str]:
        """
        Validate and sanitize Garmin credentials.
        Returns sanitized (email, password) tuple.
        Raises ServiceError if validation fails.
        """
        # Validate email
        email_result = InputValidator.validate_email(email)
        if not email_result.is_valid:
            raise ServiceError(
                "; ".join(email_result.errors),
                status_code=400,
                category=ErrorCategory.VALIDATION,
                event="garmin.credentials_invalid_email",
                context={"errors": email_result.errors},
            )
        
        # Validate password
        password_result = InputValidator.validate_password(password)
        if not password_result.is_valid:
            raise ServiceError(
                "; ".join(password_result.errors),
                status_code=400,
                category=ErrorCategory.VALIDATION,
                event="garmin.credentials_invalid_password",
                context={"errors": password_result.errors},
            )
        
        # Sanitize inputs
        sanitized_email = InputValidator.sanitize_string(email, max_length=254).lower()
        sanitized_password = password.strip()  # Don't truncate passwords
        
        return sanitized_email, sanitized_password


class DateRangeValidator:
    """Validator for date ranges."""
    
    @staticmethod
    def validate(
        start_date: Any,
        end_date: Any,
        max_days: int = 365,
    ) -> tuple[date, date]:
        """
        Validate date range.
        Returns (start_date, end_date) as date objects.
        Raises ServiceError if validation fails.
        """
        # Validate start date
        start_result = InputValidator.validate_iso_date(start_date, "start_date")
        if not start_result.is_valid:
            raise ServiceError(
                "; ".join(start_result.errors),
                status_code=400,
                category=ErrorCategory.VALIDATION,
                event="date_range.invalid_start_date",
            )
        
        # Validate end date
        end_result = InputValidator.validate_iso_date(end_date, "end_date")
        if not end_result.is_valid:
            raise ServiceError(
                "; ".join(end_result.errors),
                status_code=400,
                category=ErrorCategory.VALIDATION,
                event="date_range.invalid_end_date",
            )
        
        # Parse dates
        start = datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
        end = datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
        
        # Validate range
        if start > end:
            raise ServiceError(
                "start_date must be before end_date",
                status_code=400,
                category=ErrorCategory.VALIDATION,
                event="date_range.invalid_range",
            )
        
        # Check maximum range
        range_days = (end - start).days
        if range_days > max_days:
            raise ServiceError(
                f"Date range cannot exceed {max_days} days",
                status_code=400,
                category=ErrorCategory.VALIDATION,
                event="date_range.too_large",
                context={"range_days": range_days, "max_days": max_days},
            )
        
        return start, end


# Import unicodedata for sanitize_string
import unicodedata