// Model IDs verified against Featherless (`org/Model-Name`, HuggingFace-style
// repo naming) and Fireworks (`accounts/fireworks/models/<slug>`) catalogs.
// All four are available on both providers and support tool/function calling,
// which the agent graph relies on (news_analyst's structured sentiment JSON,
// lead_architect's order proposals). Exact slugs drift as providers update
// their catalogs — always confirm with "Test API" before relying on one live.
export const MODELS_BY_PROVIDER: Record<string, { value: string; label: string }[]> = {
  featherless: [
    { value: "moonshotai/Kimi-K2-Instruct", label: "Kimi K2 Instruct (agentic, default)" },
    { value: "deepseek-ai/DeepSeek-V3", label: "DeepSeek-V3" },
    { value: "Qwen/Qwen2.5-72B-Instruct", label: "Qwen2.5 72B Instruct" },
    { value: "meta-llama/Llama-3.3-70B-Instruct", label: "Llama 3.3 70B Instruct" },
  ],
  fireworks: [
    { value: "accounts/fireworks/models/kimi-k2-instruct", label: "Kimi K2 Instruct (agentic, default)" },
    { value: "accounts/fireworks/models/deepseek-v3", label: "DeepSeek-V3" },
    { value: "accounts/fireworks/models/qwen2p5-72b-instruct", label: "Qwen2.5 72B Instruct" },
    { value: "accounts/fireworks/models/llama-v3p3-70b-instruct", label: "Llama 3.3 70B Instruct" },
  ],
};

export const PROVIDER_LABELS: Record<string, string> = {
  featherless: "Featherless AI",
  fireworks: "Fireworks AI",
};
