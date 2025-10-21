# Troubleshooting Guide

## Known Issues

### 1. OpenAI Whisper Provider: "module 'whisper' has no attribute 'load_model'"

**Symptom:**
```
ERROR - Failed to initialize Whisper model: module 'whisper' has no attribute 'load_model'
```

**Cause:**
There's a naming conflict between two Python packages:
- `openai-whisper` (the AI speech recognition model) - imports as `whisper`
- `whisper` (Graphite's time-series database library) - also imports as `whisper`

If both packages are installed, the Graphite `whisper` module shadows the `openai-whisper` module, causing import failures.

**Solution:**

1. **Remove the conflicting package:**
   ```bash
   poetry run pip uninstall -y whisper
   ```

2. **Reinstall openai-whisper:**

   **Important:** The extra is called `openai-whisper`, not `whisper`:

   ```bash
   # Correct command:
   poetry install --extras="openai-whisper"

   # Wrong command (will fail):
   # poetry install --extras="whisper"  ❌
   ```

   **If you have network/SSL issues:**
   ```bash
   # Option 1: Use VPN (recommended)
   # Enable your VPN, then:
   poetry install --extras="openai-whisper"

   # Option 2: Disable SSL verification (not recommended, use only if VPN doesn't work)
   export PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org"
   poetry config certificates.pypi.cert false
   poetry install --extras="openai-whisper"
   ```

3. **Verify the installation:**
   ```bash
   poetry run python -c "import whisper; print('load_model:', hasattr(whisper, 'load_model'))"
   ```
   Should output: `load_model: True`

   If you get `ModuleNotFoundError: No module named 'whisper'`, the installation didn't complete. Check network and try again.

**Prevention:**
- The `whisper` (Graphite) package is not a dependency of this project
- If it appears, it's likely from a system-wide installation or another tool
- Use isolated virtual environments (poetry handles this automatically)

**Alternative:**
If you don't need the original OpenAI Whisper provider:
- Use only `faster-whisper` provider (recommended, faster and better)
- Remove `whisper` from `WHISPER_PROVIDERS` in `.env`
- Set `WHISPER_PROVIDERS=["faster-whisper"]`

---

### 2. OpenAI API 403 Forbidden Error

**Symptom:**
```
ERROR - OpenAI API client error (403): Client error '403 Forbidden' for url 'https://api.openai.com/v1/audio/transcriptions'
```

**Cause:**
One of the following:
- No API key configured
- Invalid API key
- API key doesn't have access to Whisper API
- Billing not set up on OpenAI account

**Solution:**

1. **Get an OpenAI API key:**
   - Visit: https://platform.openai.com/api-keys
   - Create a new API key
   - Add billing information (required for API access)

2. **Configure the API key:**
   Edit your `.env` file:
   ```bash
   OPENAI_API_KEY=sk-your_actual_key_here
   ```

3. **Test the key:**
   ```bash
   poetry run python -c "from openai import OpenAI; client = OpenAI(); print('API key valid')"
   ```

**Cost Information:**
- OpenAI Whisper API: $0.006 per minute of audio
- Benchmark mode with OpenAI enabled can be expensive
- Consider using `BENCHMARK_MODE=false` or removing `openai` from providers for testing

**Alternative:**
Use local providers (no API key needed):
```bash
WHISPER_PROVIDERS=["faster-whisper"]
WHISPER_ROUTING_STRATEGY=single
PRIMARY_PROVIDER=faster-whisper
```

---

### 3. OpenAI Whisper: "No such file or directory: 'ffmpeg'"

**Symptom:**
```
FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'
```

**Cause:**
The original OpenAI Whisper provider requires `ffmpeg` to decode audio files. `faster-whisper` does not have this requirement.

**Solution:**

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Verify installation:**
```bash
ffmpeg -version
```

**Note:** This is only required for the `whisper` provider. The `faster-whisper` provider works without ffmpeg.

**Known Issue with Original Whisper Provider:**

Even with ffmpeg installed, the original OpenAI Whisper provider may return empty transcriptions (0 segments) for some audio files, while `faster-whisper` handles the same files correctly. This is a known compatibility issue with the original Whisper implementation.

**Recommendation:** Use `faster-whisper` instead of the original `whisper` provider. It's faster, more reliable, and doesn't require ffmpeg.

```bash
WHISPER_PROVIDERS=["faster-whisper"]
PRIMARY_PROVIDER=faster-whisper
```

---

### 4. Network Connection Issues During Installation

**Symptom:**
```
All attempts to connect to pypi.org failed.
```

**Cause:**
- Network connectivity issues
- PyPI blocked in some regions
- Corporate firewall/proxy

**Solution:**

1. **Use VPN** (if in a restricted region)

2. **Use a mirror:**
   ```bash
   poetry config repositories.pypi-mirror https://mirrors.aliyun.com/pypi/simple/
   poetry config http-basic.pypi-mirror "" ""
   ```

3. **Install offline** (if packages are cached):
   ```bash
   poetry install --no-update
   ```

---

### 5. Model Download Delays

**Symptom:**
Long delay when initializing a model for the first time (e.g., 20+ seconds for `small` model, 60+ seconds for `medium`)

**Cause:**
Models are downloaded from Hugging Face on first use:
- `tiny`: ~75 MB
- `base`: ~140 MB
- `small`: ~460 MB
- `medium`: ~1.5 GB
- `large-v3`: ~2.9 GB

**Solution:**
This is expected behavior. Models are cached after first download.

**Pre-download models:**
```bash
poetry run python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
```

**Cache location:**
- Default: `~/.cache/huggingface/hub/`
- Check with: `ls -lh ~/.cache/huggingface/hub/`

---

### 6. High Memory Usage with Large Models

**Symptom:**
System becomes slow or runs out of memory when using `medium` or `large` models

**Cause:**
Large models require significant RAM:
- `tiny`: ~40 MB RAM
- `base`: ~140 MB RAM
- `small`: ~480 MB RAM
- `medium`: ~1.5 GB RAM
- `large-v3`: ~3 GB RAM

**Solution:**

1. **Use smaller models:**
   ```bash
   FASTER_WHISPER_MODEL_SIZE=small  # Instead of medium
   ```

2. **Use int8 quantization:**
   ```bash
   FASTER_WHISPER_COMPUTE_TYPE=int8  # Instead of float32
   ```

3. **Reduce concurrent workers:**
   ```bash
   MAX_CONCURRENT_WORKERS=1  # Instead of 3
   ```

---

### 7. Slow Transcription Speed

**Symptom:**
Transcription takes longer than the audio duration (RTF > 1.0)

**RTF Benchmarks (8-second audio on CPU):**
- `tiny/int8`: RTF 0.93x (7.5s)
- `base/int8`: RTF 0.21x (1.7s) ⭐ Best balance
- `small/int8`: RTF 0.34x (2.7s)
- `medium/int8`: RTF 0.74x (6.0s)

**Solutions:**

1. **Use faster models:**
   - `base` is fastest with good quality
   - `tiny` is fast but lower quality
   - Avoid `medium`/`large` on CPU

2. **Optimize settings:**
   ```bash
   FASTER_WHISPER_MODEL_SIZE=base
   FASTER_WHISPER_COMPUTE_TYPE=int8
   FASTER_WHISPER_BEAM_SIZE=5
   FASTER_WHISPER_VAD_FILTER=true
   ```

3. **Use GPU** (if available):
   ```bash
   FASTER_WHISPER_DEVICE=cuda
   FASTER_WHISPER_COMPUTE_TYPE=float16
   ```

---

## Benchmark Results

From the test run (8-second Russian audio on CPU):

| Configuration | Time | RTF | Text Length | Notes |
|--------------|------|-----|-------------|-------|
| faster-whisper/base/int8/beam5 | 1.73s | 0.21x | 120 chars | ⭐ **Recommended** |
| faster-whisper/tiny/int8/beam5 | 7.51s | 0.93x | 66 chars | Fast but lower quality |
| faster-whisper/small/int8/beam5 | 2.73s | 0.34x | 96 chars | Good balance |
| faster-whisper/small/int8/beam10 | 2.63s | 0.33x | 101 chars | Better quality, similar speed |
| faster-whisper/small/float32/beam5 | 3.59s | 0.44x | 77 chars | Slower, no quality benefit |
| faster-whisper/medium/int8/beam5 | 5.99s | 0.74x | 101 chars | Too slow for CPU |
| whisper/base | ❌ Failed | - | - | Module conflict |
| whisper/small | ❌ Failed | - | - | Module conflict |
| openai | ❌ Failed (403) | - | - | No API key |

**Recommendation:** Use `base` model with `int8` compute type for best speed/quality trade-off on CPU.

---

## Getting Help

1. **Check logs:**
   ```bash
   LOG_LEVEL=DEBUG poetry run python -m src.main
   ```

2. **Test configuration:**
   ```bash
   poetry run python -c "from src.config import settings; print(settings.model_dump_json(indent=2))"
   ```

3. **Verify installations:**
   ```bash
   poetry show | grep whisper
   poetry show | grep openai
   ```

4. **Check system resources:**
   ```bash
   # Memory
   free -h  # Linux
   vm_stat  # macOS

   # Disk space for model cache
   du -sh ~/.cache/huggingface/
   ```

5. **Report issues:**
   - GitHub: https://github.com/konstantinbalakin/telegram-voice2text-bot/issues
   - Include: logs, OS, Python version, configuration (.env with secrets removed)
