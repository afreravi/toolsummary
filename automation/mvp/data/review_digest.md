# Daily review digest - 2026-10-28

Automation refreshed the pricing dataset. **713 model pages** and 400 comparison pages were regenerated. No action needed unless something below looks wrong.

## Prices that moved

461 price changes in the last 30 days, 732 new models, 19 delisted.

### 317 changes over 20% - check these before trusting the page

- **DeepSeek Flash Latest** input: $0.0001 -> $0.0336 (33500.0%)
- **DeepSeek V4 Flash Latest** output: $0.0147 -> $1.28 (8607.48%)
- **DeepSeek V4.1 Flash** output: $0.0112 -> $0.525 (4587.5%)
- **DeepSeek Flash Latest** output: $0.024 -> $0.5 (1983.33%)
- **GLM 5.2** input: $0.037 -> $0.62 (1575.68%)
- **DeepSeek Pro Latest** output: $0.7484 -> $8.0 (968.95%)
- **DeepSeek V4 Flash 0731** input: $0.0422 -> $0.44 (942.65%)
- **GLM 5.3 Flash** input: $0.0052 -> $0.05 (861.54%)
- **DeepSeek V4 Flash 0731** output: $0.15 -> $1.32 (780.0%)
- **Mimo V2.5** output: $0.238 -> $2.0 (740.34%)
- **DeepSeek V4 Flash 0731** output: $0.1694 -> $1.32 (679.22%)
- **DeepSeek Pro Latest** output: $0.6574 -> $5.0 (660.57%)
- **DeepSeek V4 Flash 0731** input: $0.0094 -> $0.07 (644.68%)
- **DeepSeek V4.1 Flash** output: $0.15 -> $1.0 (566.67%)
- **Qwen 3.8 27 B** input: $0.04 -> $0.24 (500.0%)

## Needs a human decision

### 51 possible duplicates
Two model IDs look like the same product. Confirm and either merge or ignore.

- `poolside/laguna-xs-2.1:free` looks like `poolside/laguna-s-2.1:free` (similarity 0.96)
- `~deepseek/deepseek-v4-flash-latest` looks like `deepseek/deepseek-v4.1-flash:batch` (similarity 0.944)
- `meta/muse-spark-1.2-contributor` looks like `meta/muse-spark-1.3-contributor` (similarity 0.962)
- `mistral/ministral-3-3b-2512` looks like `mistralai/ministral-3b-2512` (similarity 0.944)
- `lambda_ai/llama3.3-70b-instruct-fp8` looks like `lambda_ai/llama3.1-70b-instruct-fp8` (similarity 0.96)
- `perceptron/perceptron-mk1` looks like `perceptron/perceptron-mk1.5` (similarity 0.933)
- `mistral/ministral-3-8b-2512` looks like `mistralai/ministral-8b-2512` (similarity 0.944)
- `mistral/ministral-3-14b-2512` looks like `mistralai/ministral-14b-2512` (similarity 0.947)
- `gmi/Qwen/Qwen3-VL-235B-A22B-Instruct-FP8` looks like `qwen/qwen3-vl-235b-a22b-instruct` (similarity 0.931)
- `minimax/MiniMax-M2.5-lightning` looks like `minimax/MiniMax-M2.1-lightning` (similarity 0.955)
- `google/gemini-3.7-flash:batch` looks like `google/gemini-3.8-flash:batch` (similarity 0.938)
- `google/gemini-3.6-flash:batch` looks like `google/gemini-3.8-flash:batch` (similarity 0.938)
- `mistralai/mistral-medium-3` looks like `mistralai/mistral-medium-3.1` (similarity 0.941)
- `nebius/nvidia/Llama-3_1-Nemotron-Ultra-253B-v1` looks like `nebius/nvidia/Llama-3.1-Nemotron-Ultra-253B-v1` (similarity 0.966)
- `ovhcloud/Meta-Llama-3_3-70B-Instruct` looks like `ovhcloud/Meta-Llama-3_1-70B-Instruct` (similarity 0.963)

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
