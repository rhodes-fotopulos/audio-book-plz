#!/usr/bin/env bash
set -euo pipefail

step()  { printf "\n\033[1;34m▸ %s\033[0m\n" "$1"; }
ok()    { printf "  \033[0;32m✓ %s\033[0m\n" "$1"; }
warn()  { printf "  \033[0;33m⚠ %s\033[0m\n" "$1"; }
fail()  { printf "  \033[0;31m✗ %s\033[0m\n" "$1"; exit 1; }

# 1. Apple Silicon check
step "Checking Apple Silicon"
if [ "$(uname -m)" != "arm64" ]; then
    fail "This app requires Apple Silicon (M1+)."
fi
ok "Apple Silicon detected"

# 2. RAM check
step "Checking RAM"
ram_bytes=$(sysctl -n hw.memsize)
ram_gb=$((ram_bytes / 1073741824))
if [ "$ram_gb" -lt 16 ]; then
    warn "Only ${ram_gb}GB RAM detected. 16GB recommended. Will use smaller model."
else
    ok "${ram_gb}GB RAM"
fi

# 3. Homebrew
step "Checking Homebrew"
if ! command -v brew &>/dev/null; then
    echo "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi
ok "Homebrew $(brew --version | head -1)"

# 4. Python 3.11
step "Checking Python 3.11"
if ! brew list python@3.11 &>/dev/null; then
    echo "Installing Python 3.11..."
    brew install python@3.11
fi
ok "Python 3.11 installed"

# 5. uv
step "Checking uv"
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
ok "uv $(uv --version)"

# 6. ffmpeg
step "Checking ffmpeg"
if ! command -v ffmpeg &>/dev/null; then
    echo "Installing ffmpeg..."
    brew install ffmpeg
fi
ok "ffmpeg installed"

# 7. Ollama
step "Checking Ollama"
if ! command -v ollama &>/dev/null; then
    echo "Installing Ollama..."
    brew install ollama
fi
ok "Ollama installed"

# 8. Start Ollama
step "Starting Ollama"
if ! curl -sf http://localhost:11434/api/version &>/dev/null; then
    brew services start ollama 2>/dev/null || (ollama serve &>/dev/null &)
    echo "Waiting for Ollama to start..."
    for i in $(seq 1 30); do
        if curl -sf http://localhost:11434/api/version &>/dev/null; then break; fi
        sleep 1
    done
    if ! curl -sf http://localhost:11434/api/version &>/dev/null; then
        fail "Ollama failed to start after 30 seconds."
    fi
fi
ok "Ollama running"

# 9. Pull Ollama model
step "Checking Ollama model"
if [ "$ram_gb" -ge 16 ]; then
    model="qwen3.5:9b"
else
    model="qwen3.5:4b"
fi
if ! ollama list | grep -q "$model"; then
    echo "Pulling $model (this may take a few minutes)..."
    ollama pull "$model"
fi
ok "$model ready"

# 10. Download LibriTTS-P CSVs
step "Checking LibriTTS-P data"
data_dir="$HOME/.local/share/libritts-p/data"
mkdir -p "$data_dir"
base_url="https://raw.githubusercontent.com/line/LibriTTS-P/main/data"
for csv in df1_en.csv df2_en.csv df3_en.csv; do
    if [ ! -f "$data_dir/$csv" ]; then
        echo "Downloading $csv..."
        curl -fsSL "$base_url/$csv" -o "$data_dir/$csv"
    fi
done
ok "LibriTTS-P data ready"

# 11. Create venv and install
step "Setting up Python environment"
if [ ! -d ".venv" ]; then
    uv venv --python 3.11 .venv
fi
uv pip install -e .
ok "Python dependencies installed"

# 12. Download NLTK data
step "Checking NLTK data"
.venv/bin/python -c "import nltk; nltk.download('punkt_tab', quiet=True)"
ok "NLTK data ready"

# 13. Print usage summary
printf "\n"
printf "\033[1;32m╔══════════════════════════════════════════╗\033[0m\n"
printf "\033[1;32m║       Audio Book Plz — Ready! 🎧         ║\033[0m\n"
printf "\033[1;32m╠══════════════════════════════════════════╣\033[0m\n"
printf "\033[1;32m║                                          ║\033[0m\n"
printf "\033[1;32m║  Convert a book:                         ║\033[0m\n"
printf "\033[1;32m║  audio-book-plz convert mybook.epub      ║\033[0m\n"
printf "\033[1;32m║                                          ║\033[0m\n"
printf "\033[1;32m║  Check system health:                    ║\033[0m\n"
printf "\033[1;32m║  audio-book-plz doctor                   ║\033[0m\n"
printf "\033[1;32m║                                          ║\033[0m\n"
printf "\033[1;32m╚══════════════════════════════════════════╝\033[0m\n"
