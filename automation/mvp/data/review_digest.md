# Daily review digest - 2026-10-10

Automation refreshed the pricing dataset. **662 model pages** and 400 comparison pages were regenerated. No action needed unless something below looks wrong.

## Prices that moved

27 price changes in the last 30 days, 666 new models, 4 delisted.

### 13 changes over 20% - check these before trusting the page

- **DeepSeek V4 Flash Latest** output: $0.0147 -> $1.28 (8607.48%)
- **DeepSeek V4 Pro** input: $0.2088 -> $0.9483 (354.17%)
- **DeepSeek V4 Pro** output: $0.4176 -> $1.8966 (354.17%)
- **GLM Flash Latest** output: $0.1563 -> $0.5 (219.9%)
- **DeepSeek Pro Latest** input: $0.1282 -> $0.3 (134.01%)
- **Hy 3** input: $0.0825 -> $0.132 (60.0%)
- **Hy 3** output: $0.33 -> $0.528 (60.0%)
- **DeepSeek Pro Latest** output: $8.0 -> $5.0 (-37.5%)
- **DeepSeek Flash Latest** input: $0.016 -> $0.0101 (-36.88%)
- **Kimi K3** input: $0.9 -> $0.64 (-28.89%)
- **DeepSeek V4 Flash 0731** input: $0.0064 -> $0.0047 (-26.56%)
- **GLM Latest** input: $0.0312 -> $0.039 (25.0%)
- **GLM Flash Latest** input: $0.032 -> $0.04 (25.0%)

## Needs a human decision

### 52 possible duplicates
Two model IDs look like the same product. Confirm and either merge or ignore.

- `poolside/laguna-xs-2.1:free` looks like `poolside/laguna-s-2.1:free` (similarity 0.96)
- `nebius/Qwen/Qwen3-4B` looks like `qwen/qwen3-14b` (similarity 0.941)
- `vercel_ai_gateway/alibaba/qwen-3-14b` looks like `qwen/qwen3-14b` (similarity 0.947)
- `meta/muse-spark-1.2-contributor` looks like `meta/muse-spark-1.3-contributor` (similarity 0.962)
- `mistral/ministral-3-3b-2512` looks like `mistralai/ministral-3b-2512` (similarity 0.944)
- `lambda_ai/llama3.3-70b-instruct-fp8` looks like `lambda_ai/llama3.1-70b-instruct-fp8` (similarity 0.96)
- `perceptron/perceptron-mk1` looks like `perceptron/perceptron-mk1.5` (similarity 0.933)
- `mistral/ministral-3-14b-2512` looks like `mistralai/ministral-14b-2512` (similarity 0.947)
- `gmi/Qwen/Qwen3-VL-235B-A22B-Instruct-FP8` looks like `qwen/qwen3-vl-235b-a22b-instruct` (similarity 0.931)
- `minimax/MiniMax-M2.5-lightning` looks like `minimax/MiniMax-M2.1-lightning` (similarity 0.955)
- `google/gemini-3.7-flash:batch` looks like `google/gemini-3.8-flash:batch` (similarity 0.938)
- `google/gemini-3.6-flash:batch` looks like `google/gemini-3.8-flash:batch` (similarity 0.938)
- `nebius/nvidia/Llama-3_1-Nemotron-Ultra-253B-v1` looks like `nebius/nvidia/Llama-3.1-Nemotron-Ultra-253B-v1` (similarity 0.966)
- `ovhcloud/Meta-Llama-3_3-70B-Instruct` looks like `ovhcloud/Meta-Llama-3_1-70B-Instruct` (similarity 0.963)
- `mistral/mistral-large-4` looks like `mistralai/mistral-large-4-0` (similarity 0.938)

### 36 rows missing a usable context window

- `nscale/Qwen/Qwen2.5-Coder-3B-Instruct` - 0.01 USD/1M input
- `nscale/Qwen/Qwen2.5-Coder-7B-Instruct` - 0.01 USD/1M input
- `nscale/deepseek-ai/DeepSeek-R1-Distill-Llama-8B` - 0.025 USD/1M input
- `nscale/Qwen/Qwen2.5-Coder-32B-Instruct` - 0.06 USD/1M input
- `nscale/deepseek-ai/DeepSeek-R1-Distill-Qwen-14B` - 0.07 USD/1M input
- `nscale/deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B` - 0.09 USD/1M input
- `fireworks-ai-up-to-4b` - 0.1 USD/1M input
- `together-ai-up-to-4b` - 0.1 USD/1M input
- `nscale/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B` - 0.15 USD/1M input
- `fireworks-ai-4.1b-to-16b` - 0.2 USD/1M input
- `nscale/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` - 0.2 USD/1M input
- `together-ai-4.1b-8b` - 0.2 USD/1M input
- `baseten/nvidia/Nemotron-120B-A12B` - 0.3 USD/1M input
- `together-ai-8.1b-21b` - 0.3 USD/1M input
- `fal_ai/fal-ai/moondream3-preview/query` - 0.4 USD/1M input

## Anything that moved fast

Check the git diff on `data/pricing.json`. A model whose price changed by more than 20% in one day is worth a manual look before the page is trusted.
