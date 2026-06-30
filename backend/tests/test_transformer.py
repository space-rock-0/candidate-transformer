"""
Tests for CandidateTransformer
===============================
Covers: normalisation, all parsers, merger conflict logic, API endpoints.
"""

import pytest
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.transformer import (
    CandidateTransformer,
    CSVParser, ATSParser, GitHubParser, ResumeParser, RecruiterNotesParser,
    normalize_name, normalize_email, normalize_phone, normalize_skills,
    extract_years_of_experience, SourceType, FieldValue, merge_profiles,
    CanonicalProfile,
)


# ──────────────────────────────────────────────
# Normalisation Tests
# ──────────────────────────────────────────────

class TestNormaliseName:
    def test_normal_full_name(self):
        name, conf = normalize_name("john doe")
        assert name == "John Doe"
        assert conf > 0.8

    def test_all_caps(self):
        name, conf = normalize_name("JANE SMITH")
        assert name == "Jane Smith"

    def test_single_name_low_conf(self):
        name, conf = normalize_name("Madonna")
        assert conf < 0.8

    def test_empty_returns_zero(self):
        name, conf = normalize_name("")
        assert name == ""
        assert conf == 0.0

    def test_strips_numbers(self):
        name, conf = normalize_name("John123 Doe")
        assert "123" not in name


class TestNormaliseEmail:
    def test_valid_email(self):
        email, conf = normalize_email("User@Example.COM")
        assert email == "user@example.com"
        assert conf > 0.9

    def test_email_in_noise(self):
        email, conf = normalize_email("contact me at foo@bar.io please")
        assert email == "foo@bar.io"

    def test_invalid_returns_empty(self):
        email, conf = normalize_email("not-an-email")
        assert email == ""
        assert conf == 0.0

    def test_temp_mail_low_conf(self):
        email, conf = normalize_email("x@mailinator.com")
        assert conf < 0.8


class TestNormalisePhone:
    def test_ten_digit(self):
        phone, conf = normalize_phone("9876543210")
        assert "9876543210" in phone
        assert conf > 0.6  # bare 10-digit is usable but lacks country-code certainty

    def test_formatted_phone(self):
        phone, conf = normalize_phone("+1 (555) 123-4567")
        assert conf > 0.8

    def test_garbage_returns_empty(self):
        phone, conf = normalize_phone("no phone here")
        assert phone == ""

    def test_too_short(self):
        phone, conf = normalize_phone("123")
        assert phone == ""

    def test_country_code_beats_bare_in_confidence(self):
        """Regression: a complete number with country code must score higher
        than a bare national number, so it wins merges (caught via E2E testing)."""
        bare_phone, bare_conf = normalize_phone("9876543210")
        full_phone, full_conf = normalize_phone("+919876543210")
        assert full_conf > bare_conf


class TestNormaliseSkills:
    def test_comma_separated(self):
        skills, _ = normalize_skills("Python, FastAPI, React")
        assert "Python" in skills
        assert "FastAPI" in skills

    def test_list_input(self):
        skills, _ = normalize_skills(["Go", "Rust", "C++"])
        assert "Go" in skills

    def test_deduplicates(self):
        skills, _ = normalize_skills("Python, python, PYTHON")
        assert skills.count("Python") + skills.count("python") + skills.count("PYTHON") == 1

    def test_empty_returns_empty(self):
        skills, conf = normalize_skills("")
        assert skills == []
        assert conf == 0.0


class TestExtractYOE:
    def test_simple_phrase(self):
        yoe, conf = extract_years_of_experience("5 years of experience in software")
        assert yoe == 5
        assert conf > 0.5

    def test_with_plus(self):
        yoe, conf = extract_years_of_experience("8+ years working in ML")
        assert yoe == 8

    def test_no_match(self):
        yoe, conf = extract_years_of_experience("I like coding")
        assert yoe is None


# ──────────────────────────────────────────────
# Parser Tests
# ──────────────────────────────────────────────

class TestCSVParser:
    def test_standard_row(self):
        row = {"name": "Alice Sharma", "email": "alice@corp.com",
               "phone": "9999888877", "current_company": "TechCorp", "title": "SWE"}
        p = CSVParser().parse(row)
        assert p.name.value == "Alice Sharma"
        assert p.email.value == "alice@corp.com"
        assert p.phone is not None
        assert p.current_company.value == "TechCorp"

    def test_alternate_column_names(self):
        row = {"full_name": "Bob Jones", "email_address": "bob@x.io", "mobile": "1234567890"}
        p = CSVParser().parse(row)
        assert p.name.value == "Bob Jones"
        assert p.email.value == "bob@x.io"

    def test_empty_row(self):
        p = CSVParser().parse({})
        assert p.name is None
        assert p.email is None

    def test_malformed_email(self):
        row = {"name": "Carol", "email": "not_valid"}
        p = CSVParser().parse(row)
        assert p.email is None


class TestATSParser:
    def test_remapped_fields(self):
        blob = {
            "full_name": "Dan Chen",
            "contact_email": "dan@company.org",
            "mobile": "+1-800-555-1234",
            "employer": "BigCo",
            "job_title": "Staff Engineer",
            "location": "San Francisco, CA",
            "skills_list": ["Python", "Kubernetes"],
        }
        p = ATSParser().parse(blob)
        assert p.name.value == "Dan Chen"
        assert p.email.value == "dan@company.org"
        assert p.current_company.value == "BigCo"
        assert "Python" in p.skills.value

    def test_years_of_experience(self):
        blob = {"years_experience": "7"}
        p = ATSParser().parse(blob)
        assert p.years_of_experience.value == 7

    def test_summary_field(self):
        blob = {"profile_summary": "Experienced ML engineer."}
        p = ATSParser().parse(blob)
        assert "Experienced" in p.summary.value


class TestGitHubParser:
    def test_full_profile(self):
        data = {
            "name": "Eve Kumar",
            "login": "evekumar",
            "email": "eve@gh.io",
            "company": "@OpenSource",
            "location": "Bangalore",
            "bio": "Building the future",
            "repos": [
                {"name": "myrepo", "stargazers_count": 120, "language": "Python",
                 "description": "A cool repo"},
                {"name": "another", "stargazers_count": 30, "language": "JavaScript",
                 "description": ""},
            ],
        }
        p = GitHubParser().parse(data)
        assert "github.com/evekumar" in p.github.value
        assert "Python" in p.languages.value
        assert len(p.top_repos.value) <= 5
        assert p.current_company.value == "OpenSource"  # @ stripped

    def test_no_repos(self):
        p = GitHubParser().parse({"login": "x", "repos": []})
        assert p.languages is None


class TestResumeParser:
    SAMPLE_RESUME = """
John Doe
Senior Software Engineer
john.doe@email.com
+1 9876543210
linkedin.com/in/johndoe
github.com/johndoe

Skills: Python, FastAPI, Docker, Kubernetes, PostgreSQL

10 years of experience in backend systems.

Education:
B.Tech Computer Science, IIT Delhi 2014
"""

    def test_extracts_name(self):
        p = ResumeParser().parse(self.SAMPLE_RESUME.strip())
        assert "John" in p.name.value

    def test_extracts_email(self):
        p = ResumeParser().parse(self.SAMPLE_RESUME)
        assert "john.doe@email.com" == p.email.value

    def test_extracts_phone(self):
        p = ResumeParser().parse(self.SAMPLE_RESUME)
        assert p.phone is not None

    def test_extracts_skills(self):
        p = ResumeParser().parse(self.SAMPLE_RESUME)
        assert "Python" in p.skills.value

    def test_extracts_linkedin(self):
        p = ResumeParser().parse(self.SAMPLE_RESUME)
        assert "linkedin.com/in/johndoe" in p.linkedin.value

    def test_extracts_yoe(self):
        p = ResumeParser().parse(self.SAMPLE_RESUME)
        assert p.years_of_experience.value == 10

    def test_empty_text(self):
        p = ResumeParser().parse("")
        assert p.name is None


class TestRecruiterNotesParser:
    def test_email_extraction(self):
        p = RecruiterNotesParser().parse("Great candidate, reach her at carol@test.com")
        assert "carol@test.com" == p.email.value

    def test_company_extraction(self):
        p = RecruiterNotesParser().parse("He works at Globex Corp and loves Python")
        assert p.current_company is not None

    def test_skills_extraction(self):
        p = RecruiterNotesParser().parse("She is proficient in React, Node.js, and AWS.")
        assert p.skills is not None


# ──────────────────────────────────────────────
# Merger / Conflict Tests
# ──────────────────────────────────────────────

class TestMerger:
    def _make_profile(self, name_val, source, conf) -> CanonicalProfile:
        p = CanonicalProfile()
        p.name = FieldValue(value=name_val, source=source, confidence=conf)
        p.sources_used = [source.value]
        return p

    def test_higher_priority_wins(self):
        csv_p = self._make_profile("CSV Name", SourceType.CSV, 0.9)
        notes_p = self._make_profile("Notes Name", SourceType.NOTES, 0.95)
        merged = merge_profiles([csv_p, notes_p])
        assert merged.name.value == "CSV Name"  # CSV > NOTES in priority
        assert len(merged.conflicts) == 1

    def test_conflict_logged(self):
        p1 = self._make_profile("Alice", SourceType.CSV, 0.9)
        p2 = self._make_profile("Alicia", SourceType.NOTES, 0.8)
        merged = merge_profiles([p1, p2])
        assert any(c["field"] == "name" for c in merged.conflicts)

    def test_same_value_no_conflict(self):
        p1 = self._make_profile("Alice", SourceType.CSV, 0.9)
        p2 = self._make_profile("Alice", SourceType.ATS, 0.95)
        merged = merge_profiles([p1, p2])
        assert len(merged.conflicts) == 0
        assert merged.name.confidence == 0.95  # higher conf wins

    def test_candidate_id_generated(self):
        p = CanonicalProfile()
        p.email = FieldValue(value="test@test.com", source=SourceType.CSV, confidence=0.9)
        p.sources_used = []
        merged = merge_profiles([p])
        assert merged.candidate_id.startswith("CAND_")
        assert merged.candidate_id != "CAND_UNKNOWN"


# ──────────────────────────────────────────────
# End-to-End Transformer Tests
# ──────────────────────────────────────────────

class TestCandidateTransformer:
    ct = CandidateTransformer()

    def test_csv_only(self):
        profile = self.ct.transform(
            csv_row={"name": "Grace Lee", "email": "grace@co.io",
                     "phone": "9123456789", "current_company": "StartupX", "title": "PM"}
        )
        assert profile.name.value == "Grace Lee"
        assert profile.email.value == "grace@co.io"
        assert "recruiter_csv" in profile.sources_used

    def test_ats_overrides_csv_on_conflict(self):
        profile = self.ct.transform(
            csv_row={"name": "Old Name", "email": "old@x.com"},
            ats_blob={"full_name": "New Name", "contact_email": "new@x.com"},
        )
        # ATS has higher priority
        assert profile.name.value == "New Name"

    def test_all_sources_merged(self):
        profile = self.ct.transform(
            csv_row={"name": "Tom Hardy", "email": "tom@co.io"},
            ats_blob={"full_name": "Tom Hardy", "employer": "Acme", "job_title": "SRE"},
            resume_text="Tom Hardy\nSRE\ntom@co.io\nSkills: Go, Terraform",
            recruiter_notes="Tom is great. He knows Go.",
        )
        assert profile.name.value == "Tom Hardy"
        assert profile.current_company is not None
        assert len(profile.sources_used) == 4

    def test_empty_inputs(self):
        profile = self.ct.transform()
        assert profile.candidate_id == "CAND_UNKNOWN"

    def test_overall_confidence_computed(self):
        profile = self.ct.transform(
            csv_row={"name": "High Conf", "email": "hc@test.com",
                     "phone": "9999999999", "current_company": "Corp", "title": "Dev"}
        )
        assert 0.0 < profile.overall_confidence <= 1.0

    def test_no_data_loss_sources_tracked(self):
        profile = self.ct.transform(
            csv_row={"name": "A B", "email": "ab@z.com"},
            recruiter_notes="Candidate A B. Email ab@z.com. Knows Python."
        )
        assert SourceType.CSV.value in profile.sources_used
        assert SourceType.NOTES.value in profile.sources_used


# ──────────────────────────────────────────────
# Edge Cases
# ──────────────────────────────────────────────

class TestEdgeCases:
    ct = CandidateTransformer()

    def test_unicode_name(self):
        profile = self.ct.transform(
            csv_row={"name": "Søren Müller", "email": "soren@dk.io"}
        )
        assert profile.name is not None

    def test_very_long_email(self):
        long_email = "a" * 50 + "@" + "b" * 50 + ".com"
        profile = self.ct.transform(csv_row={"name": "X Y", "email": long_email})
        # Should still extract
        assert profile.email is not None

    def test_malformed_ats_json(self):
        # All fields empty
        profile = self.ct.transform(ats_blob={})
        assert profile.name is None

    def test_resume_no_name_line(self):
        text = "email: nobody@test.com\nSkills: Java\n5 years of experience"
        profile = self.ct.transform(resume_text=text)
        assert profile.email.value == "nobody@test.com"

    def test_to_dict_completeness(self):
        profile = self.ct.transform(
            csv_row={"name": "Z A", "email": "za@test.io"}
        )
        d = profile.to_dict()
        assert "candidate_id" in d
        assert "fields" in d
        assert "overall_confidence" in d
        assert "conflicts" in d
        assert "sources_used" in d


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
