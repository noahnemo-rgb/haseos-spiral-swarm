from huggingface_hub import snapshot_download
print("Starting reliable download of BitNet BF16 model...")
snapshot_download(
    repo_id="microsoft/bitnet-b1.58-2B-4T-bf16",
    local_dir="models/bitnet-b1.58-2B-4T-bf16",
    resume_download=True,
    allow_patterns=["*"],
    tqdm_class=None
)
print("✅ Download completed successfully!")