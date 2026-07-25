"""Sapphire content engine.

Generates data-driven reports from Sapphire's real intelligence data
(predictions, portfolio, threat intel, signals) and formats them for
LinkedIn, Substack, and X, in English and Spanish. Every claim is tied
to a Sapphire data source.

Public surface:
    report_generator.WeeklyCryptoBrief
    report_generator.AIIntelReport
    report_generator.SecurityDigest
    formatters.format_linkedin / format_substack / format_x_thread
    quality.check / QualityReport
    scheduler.today_plan / plan_for
    outreach.build_bd_message
    publisher.publish
    glossary.GLOSSARY / lookup / Term
    translator.Translator / translate_text / detect_artifacts
"""

from . import (
    formatters,
    glossary,
    outreach,
    publisher,
    quality,
    report_generator,
    scheduler,
    translator,
)

__all__ = [
    "formatters",
    "glossary",
    "outreach",
    "publisher",
    "quality",
    "report_generator",
    "scheduler",
    "translator",
]
