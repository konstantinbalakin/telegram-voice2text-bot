"""Data models for transcription system."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class TranscriptionSegment:
    """Segment from faster-whisper with timestamp information."""

    start: float  # Start time in seconds
    end: float  # End time in seconds
    text: str  # Segment text


@dataclass
class TranscriptionContext:
    """Context information for transcription and routing decisions."""

    user_id: int = 0
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    language: Optional[str] = "ru"
    priority: str = "normal"  # normal, high
    provider_preference: Optional[str] = None  # Preferred provider or model
    disable_refinement: bool = False  # Skip LLM refinement (for retranscription)


@dataclass
class TranscriptionResult:
    """Result of transcription with comprehensive metrics."""

    # Core results
    text: str
    language: str
    confidence: Optional[float] = None

    # Performance metrics
    processing_time: float = 0.0  # Wall clock time in seconds
    audio_duration: float = 0.0  # Actual audio length in seconds

    # Provider info
    provider_used: str = ""  # "faster-whisper", "openai", "whisper"
    model_name: str = ""  # "large-v3", "whisper-1", etc.

    # Resource usage (for local models)
    peak_memory_mb: Optional[float] = None
    cpu_percent: Optional[float] = None

    # Segments with timestamps (for interactive features)
    segments: Optional[list[TranscriptionSegment]] = None

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    config: Optional["BenchmarkConfig"] = None
    error: Optional[str] = None

    @property
    def realtime_factor(self) -> float:
        """Calculate realtime factor (processing_time / audio_duration)."""
        if self.audio_duration == 0:
            return 0.0
        return self.processing_time / self.audio_duration

    def __str__(self) -> str:
        """Pretty print for comparison."""
        return (
            f"Provider: {self.provider_used} ({self.model_name})\n"
            f"Text: {self.text[:100]}...\n"
            f"Language: {self.language}\n"
            f"Audio: {self.audio_duration:.1f}s\n"
            f"Processing: {self.processing_time:.2f}s\n"
            f"Realtime Factor: {self.realtime_factor:.2f}x\n"
            f"Memory: {self.peak_memory_mb:.0f} MB\n"
            if self.peak_memory_mb
            else ""
        )


@dataclass
class BenchmarkConfig:
    """Configuration for one benchmark test."""

    provider_name: str  # "faster-whisper", "openai", "whisper"

    # Provider-specific settings
    model_size: Optional[str] = None  # "base", "small", "medium", etc.
    compute_type: Optional[str] = None  # "int8", "float32"
    beam_size: Optional[int] = None  # 1, 5, 10
    device: Optional[str] = None  # "cpu", "cuda"

    # Display name for report
    display_name: Optional[str] = None  # Auto-generated if None

    def __post_init__(self) -> None:
        """Generate display name if not provided."""
        if self.display_name is None:
            parts = [self.provider_name]
            if self.model_size:
                parts.append(self.model_size)
            if self.compute_type:
                parts.append(self.compute_type)
            if self.beam_size:
                parts.append(f"beam{self.beam_size}")
            self.display_name = " / ".join(parts)


@dataclass
class BenchmarkReport:
    """Comprehensive benchmark comparison report."""

    results: list[TranscriptionResult]
    reference_text: Optional[str]  # OpenAI result for quality comparison
    audio_path: Path
    audio_duration: float
    timestamp: datetime = field(default_factory=datetime.now)

    def get_sorted_by_speed(self) -> list[TranscriptionResult]:
        """Sort results by processing time (fastest first)."""
        return sorted([r for r in self.results if r.error is None], key=lambda r: r.processing_time)

    def get_sorted_by_quality(self) -> list[TranscriptionResult]:
        """Sort by text similarity to reference (if available)."""
        if not self.reference_text:
            return self.results

        # Calculate similarity scores
        scored = []
        for result in self.results:
            if result.error is None:
                similarity = self._calculate_similarity(result.text, self.reference_text)
                scored.append((result, similarity))

        return [r for r, _ in sorted(scored, key=lambda x: x[1], reverse=True)]

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate text similarity using Jaccard similarity (word overlap).

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score between 0.0 and 1.0
        """
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union)  # Jaccard similarity

    def to_markdown(self) -> str:
        """Generate markdown report for easy viewing."""
        lines = []

        lines.append("# 🔬 Whisper Models Benchmark Report")
        lines.append("")
        lines.append(f"**Audio File:** `{self.audio_path.name}`")
        lines.append(f"**Duration:** {self.audio_duration:.1f}s")
        lines.append(f"**Timestamp:** {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Reference text
        if self.reference_text:
            lines.append("## 📝 Reference Transcription (OpenAI)")
            lines.append("")
            lines.append(f"> {self.reference_text}")
            lines.append("")

        # Performance comparison table
        lines.append("## ⚡ Performance Comparison")
        lines.append("")
        lines.append("| Rank | Configuration | Processing Time | RTF | Memory | Quality Score |")
        lines.append("|------|--------------|-----------------|-----|--------|---------------|")

        sorted_by_speed = self.get_sorted_by_speed()
        for rank, result in enumerate(sorted_by_speed, 1):
            quality_score = "N/A"
            if self.reference_text and result.config and result.config.provider_name != "openai":
                similarity = self._calculate_similarity(result.text, self.reference_text)
                quality_score = f"{similarity:.2%}"
            elif result.config and result.config.provider_name == "openai":
                quality_score = "100% (ref)"

            memory_str = f"{result.peak_memory_mb:.0f} MB" if result.peak_memory_mb else "N/A"
            config_name = result.config.display_name if result.config else result.provider_used

            lines.append(
                f"| {rank} | {config_name} | "
                f"{result.processing_time:.2f}s | "
                f"{result.realtime_factor:.2f}x | "
                f"{memory_str} | "
                f"{quality_score} |"
            )

        lines.append("")

        # Quality comparison
        if self.reference_text:
            lines.append("## 🎯 Quality Ranking (vs OpenAI Reference)")
            lines.append("")
            lines.append("| Rank | Configuration | Similarity | Text Sample |")
            lines.append("|------|--------------|------------|-------------|")

            sorted_by_quality = self.get_sorted_by_quality()
            for rank, result in enumerate(sorted_by_quality, 1):
                if result.config and result.config.provider_name == "openai":
                    similarity_str = "100% (ref)"
                else:
                    similarity = self._calculate_similarity(result.text, self.reference_text)
                    similarity_str = f"{similarity:.2%}"

                text_sample = result.text[:50] + "..." if len(result.text) > 50 else result.text
                config_name = result.config.display_name if result.config else result.provider_used

                lines.append(
                    f"| {rank} | {config_name} | " f"{similarity_str} | " f"{text_sample} |"
                )

            lines.append("")

        # Detailed results
        lines.append("## 📊 Detailed Results")
        lines.append("")

        for result in self.results:
            config_name = result.config.display_name if result.config else result.provider_used
            lines.append(f"### {config_name}")
            lines.append("")

            if result.error:
                lines.append(f"**❌ Error:** {result.error}")
                lines.append("")
                continue

            lines.append(f"- **Text:** {result.text}")
            lines.append(f"- **Language:** {result.language}")
            lines.append(f"- **Processing Time:** {result.processing_time:.2f}s")
            lines.append(f"- **Realtime Factor:** {result.realtime_factor:.2f}x")

            if result.peak_memory_mb:
                lines.append(f"- **Memory Usage:** {result.peak_memory_mb:.0f} MB")

            if self.reference_text and result.config and result.config.provider_name != "openai":
                similarity = self._calculate_similarity(result.text, self.reference_text)
                lines.append(f"- **Quality Score:** {similarity:.2%}")

            lines.append("")

        # Recommendations
        lines.append("## 💡 Recommendations")
        lines.append("")

        # Find best speed
        sorted_by_speed = self.get_sorted_by_speed()
        if sorted_by_speed:
            best_speed = sorted_by_speed[0]
            config_name = (
                best_speed.config.display_name if best_speed.config else best_speed.provider_used
            )
            lines.append(
                f"- **Fastest:** {config_name} "
                f"({best_speed.processing_time:.2f}s, RTF: {best_speed.realtime_factor:.2f}x)"
            )

        if self.reference_text:
            sorted_by_quality = self.get_sorted_by_quality()
            if sorted_by_quality:
                best_quality = sorted_by_quality[0]
                if best_quality.config and best_quality.config.provider_name != "openai":
                    similarity = self._calculate_similarity(best_quality.text, self.reference_text)
                    config_name = best_quality.config.display_name
                    lines.append(
                        f"- **Best Quality:** {config_name} "
                        f"({similarity:.2%} similarity to OpenAI)"
                    )

            # Find best balance (quality > 90%, fastest)
            balanced = None
            for result in sorted_by_speed:
                if result.config and result.config.provider_name == "openai":
                    continue
                similarity = self._calculate_similarity(result.text, self.reference_text)
                if similarity >= 0.90:
                    balanced = result
                    break

            if balanced and balanced.config:
                similarity = self._calculate_similarity(balanced.text, self.reference_text)
                lines.append(
                    f"- **Best Balance:** {balanced.config.display_name} "
                    f"({similarity:.2%} quality, {balanced.realtime_factor:.2f}x RTF)"
                )

        return "\n".join(lines)

    def save_to_file(self, output_dir: Path) -> Path:
        """
        Save report to markdown file.

        Args:
            output_dir: Directory to save report

        Returns:
            Path to saved report file
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"benchmark_{self.timestamp.strftime('%Y%m%d_%H%M%S')}.md"
        output_path = output_dir / filename

        output_path.write_text(self.to_markdown())

        return output_path
