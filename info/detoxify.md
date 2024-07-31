# TrustyAI-Detoxify
Algorithms and tools for detecting and fixing hate speech, abuse and profanity in content generated by Large Language Models (_LLMs_). The source code is located in the [trustyai.language.detoxify](https://github.com/trustyai-explainability/trustyai-explainability-python/tree/main/src/trustyai/language/detoxify) module.

## T-MaRCo

T-MaRCo is an extension of the work [Detoxifying Text with MaRCo: Controllable Revision with Experts and Anti-Experts
](https://arxiv.org/abs/2212.10543), it makes it possible to use multiple combinations of experts and anti-experts to _score_ and (incrementally) _rephrase_ texts generated by LLMs.

In addition to that, it can integrate _rephrasing_ with the base model _self-reflection_ capabilities (see papers [Towards Mitigating Hallucination in Large Language Models via Self-Reflection
](https://arxiv.org/abs/2310.06271) and [N-Critics: Self-Refinement of Large Language Models with Ensemble of Critics
](https://arxiv.org/abs/2310.18679)).

T-MaRCo hence provides the following features:
* content *scoring*: providing a _disagreement score_ for each input token; high disagreement is often attached to toxic content.
* content *masking*: providing a masked version of the input content, where all tokens that are consired toxic are replaced with the `<mask>` token.
* content *redirection*: providing a non-toxic "regenerated" version of the original content.

How to use T-MaRCo:
```python
from trustyai.detoxify import TMaRCo

# instantiate T-MaRCo
tmarco = TMaRCo(expert_weights=[-1, 2])

# load pretrained anti-expert and expert models
tmarco.load_models(["trustyai/gminus", "trustyai/gplus"])

# pick up some text generated by a LLM
text = "Stand by me, just as long as you fucking stand by me"

# generate T-MaRCo disagreement scores
scores = tmarco.score([text]) # '[0.78664607 0.06622718 0.02403926 5.331921 0.49842355 0.46609956 0.22441313 0.43487906 0.51990145 1.9062967  0.64200985 0.30269763 1.7964466 ]'

# mask tokens having high disagreement scores
masked_text = tmarco.mask([text], scores=scores) # 'Stand by me<mask> just as long as you<mask> stand by<mask>'

# rephrase masked tokens
rephrased = tmarco.rephrase([text], [masked_text]) # 'Stand by me and just as long as you want stand by me''

# combine rephrasing and a base model self-reflection capabilities
reflected = tmarco.reflect([text]) # '["'Stand by me in the way I want stand by you and in the ways I need you to standby me'."]'

```

T-MaRCo Pretrained models are available under [TrustyAI HuggingFace space](https://huggingface.co/trustyai) at https://huggingface.co/trustyai/gminus and https://huggingface.co/trustyai/gplus.