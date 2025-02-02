from typing import List, Dict, Optional
from enum import Enum
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from know_lang_bot.config import AppConfig
from know_lang_bot.utils.model_provider import create_pydantic_model
from know_lang_bot.chat_bot.chat_graph import ChatResult
import json
import asyncio

class EvalMetric(str, Enum):
    CHUNK_RELEVANCE = "chunk_relevance"
    ANSWER_CORRECTNESS = "answer_correctness"
    CODE_REFERENCE = "code_reference"

class EvalCase(BaseModel):
    """Single evaluation case focused on code understanding"""
    question: str
    expected_files: List[str] = Field(description="Files that should be in retrieved chunks")
    expected_concepts: List[str] = Field(description="Key concepts that should be in answer")
    expected_code_refs: List[str] = Field(description="Code references that should be mentioned")
    difficulty: int = Field(ge=1, le=3, description="1: Easy, 2: Medium, 3: Hard")

class EvalResult(BaseModel):
    """Evaluation result with scores and feedback"""
    case: EvalCase
    metrics: Dict[EvalMetric, float]
    total_score: float
    feedback: str
    polished_question: Optional[str] = None

class EvalAgentResponse(BaseModel):
    chunk_relevance: float
    answer_correctness: float
    code_reference: float
    feedback: str


class ChatBotEvaluationContext(EvalCase, ChatResult):
    pass

    
class ChatBotEvaluator:
    def __init__(self, config: AppConfig):
        """Initialize evaluator with app config"""
        self.config = config
        self.eval_agent = Agent(
            create_pydantic_model(
                model_provider=config.llm.model_provider,
                model_name=config.llm.model_name
            ),
            system_prompt=self._build_eval_prompt(),
            result_type=EvalAgentResponse
        )

    def _build_eval_prompt(self) -> str:
        return """You are an expert evaluator of code understanding systems.
Evaluate the response based on these specific criteria:

1. Chunk Relevance (0-1):
- Are the retrieved code chunks from the expected files?
- Do they contain relevant code sections?

2. Answer Correctness (0-1):
- Does the answer accurately explain the code?
- Are the expected concepts covered?

3. Code Reference Quality (0-1):
- Does it properly cite specific code locations?
- Are code references clear and relevant?
}"""

    async def evaluate_single(
        self,
        case: EvalCase,
        chat_result: ChatResult
    ) -> EvalResult:
        """Evaluate a single case"""
        # Prepare evaluation context
        eval_context = ChatBotEvaluationContext(
            **case.model_dump(),
            **chat_result.model_dump()
        )

        # Get evaluation from the model
        result = await self.eval_agent.run(
            json.dumps(eval_context),
        )
        metrics = result.data

        # Calculate weighted score
        weights = {
            EvalMetric.CHUNK_RELEVANCE: 0.4,
            EvalMetric.ANSWER_CORRECTNESS: 0.4,
            EvalMetric.CODE_REFERENCE: 0.2
        }
        
        total_score = sum(
            metrics[metric] * weights[metric] * case.difficulty
            for metric in EvalMetric
        )

        return EvalResult(
            case=case,
            metrics=metrics,
            total_score=total_score,
            feedback=metrics["feedback"]
        )

    async def evaluate_batch(
        self,
        cases: List[EvalCase],
        process_chat_func,
        max_concurrent: int = 2
    ) -> List[EvalResult]:
        """Run evaluation on multiple cases with concurrency control"""
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def eval_single_with_limit(case: EvalCase) -> EvalResult:
            async with semaphore:
                chat_result = await process_chat_func(case.question)
                return await self.evaluate_single(case, chat_result)

        return await asyncio.gather(
            *[eval_single_with_limit(case) for case in cases]
        )

# src/transformers/quantizers/base.py
TRANSFORMER_QUANTIZER_BASE_CASES = [
    EvalCase(
        question= "How are different quantization methods implemented in the transformers library, and what are the key components required to implement a new quantization method?",
        expected_files= ["quantizers/base.py"],
        expected_concepts= [
            "HfQuantizer abstract base class",
            "PreTrainedModel quantization",
            "pre/post processing of models",
            "quantization configuration", 
            "requires_calibration flag"
        ],
        expected_code_refs= [
            "class HfQuantizer",
            "preprocess_model method",
            "postprocess_model method",
            "_process_model_before_weight_loading",
            "requires_calibration attribute"
        ],
        difficulty= 3
    )
]

# src/transformers/quantizers/auto.py
TRANSFORMER_QUANTIZER_AUTO_CASES = [
    EvalCase(
        question="How does the transformers library automatically select and configure the appropriate quantization method, and what happens when loading a pre-quantized model?",
        expected_files=[
            "quantizers/auto.py",
            "utils/quantization_config.py"
        ],
        expected_concepts=[
            "automatic quantizer selection",
            "quantization config mapping",
            "config merging behavior",
            "backwards compatibility for bitsandbytes",
            "quantization method resolution"
        ],
        expected_code_refs=[
            "AUTO_QUANTIZER_MAPPING",
            "AUTO_QUANTIZATION_CONFIG_MAPPING",
            "AutoHfQuantizer.from_config",
            "AutoQuantizationConfig.from_pretrained",
            "merge_quantization_configs method"
        ],
        difficulty=3
    )
]


# src/transformers/pipelines/base.py
TRANSFORMER_PIPELINE_BASE_TEST_CASES = [
    EvalCase(
        question="How does the Pipeline class handle model and device initialization?",
        expected_files=["base.py"],
        expected_concepts=[
            "device placement",
            "model initialization",
            "framework detection",
            "device type detection",
            "torch dtype handling"
        ],
        expected_code_refs=[
            "def __init__",
            "def device_placement",
            "infer_framework_load_model",
            "self.device = torch.device"
        ],
        difficulty=3
    ),
    EvalCase(
        question="How does the Pipeline class implement batched inference and data loading?",
        expected_files=["base.py", "pt_utils.py"],
        expected_concepts=[
            "batch processing",
            "data loading",
            "collate function",
            "padding implementation",
            "iterator pattern"
        ],
        expected_code_refs=[
            "def get_iterator",
            "class PipelineDataset",
            "class PipelineIterator",
            "_pad",
            "pad_collate_fn"
        ],
        difficulty=3
    )
]

# src/transformers/pipelines/text_generation.py
TRANSFORMER_PIPELINE_TEXT_GENERATION_TEST_CASES = [
    EvalCase(
        question="How does the TextGenerationPipeline handle chat-based generation and template processing?",
        expected_files=["text_generation.py", "base.py"],
        expected_concepts=[
            "chat message formatting",
            "template application",
            "message continuation",
            "role handling",
            "assistant prefill behavior"
        ],
        expected_code_refs=[
            "class Chat",
            "tokenizer.apply_chat_template",
            "continue_final_message",
            "isinstance(prompt_text, Chat)",
            "postprocess"
        ],
        difficulty=3
    )
]

# src/transformers/generation/logits_process.py
TRANSFORMER_LOGITS_PROCESSOR_TEST_CASES = [
    EvalCase(
        question="How does TopKLogitsWarper implement top-k filtering for text generation?",
        expected_files=["generation/logits_process.py"],
        expected_concepts=[
            "top-k filtering algorithm",
            "probability masking",
            "batch processing",
            "logits manipulation",
            "vocabulary filtering"
        ],
        expected_code_refs=[
            "class TopKLogitsWarper(LogitsProcessor)",
            "torch.topk(scores, top_k)[0]",
            "indices_to_remove = scores < torch.topk",
            "scores_processed = scores.masked_fill(indices_to_remove, self.filter_value)",
            "top_k = max(top_k, min_tokens_to_keep)"
        ],
        difficulty=3
    ),
    EvalCase(
        question="How does TemperatureLogitsProcessor implement temperature sampling for controlling generation randomness?",
        expected_files=["generation/logits_process.py"],
        expected_concepts=[
            "temperature scaling",
            "probability distribution shaping",
            "logits normalization",
            "generation randomness control",
            "batch processing with temperature"
        ],
        expected_code_refs=[
            "class TemperatureLogitsProcessor(LogitsProcessor)",
            "scores_processed = scores / self.temperature",
            "if not isinstance(temperature, float) or not (temperature > 0)",
            "def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor)",
            "raise ValueError(except_msg)"
        ],
        difficulty=3
    )
]

# src/transformers/trainer.py
TRANSFORMER_TRAINER_TEST_CASES = [
    EvalCase(
        question="How does Trainer handle distributed training and gradient accumulation? Explain the implementation details.",
        expected_files=["trainer.py"],
        expected_concepts=[
            "gradient accumulation steps",
            "distributed training logic",
            "optimizer step scheduling",
            "loss scaling",
            "device synchronization"
        ],
        expected_code_refs=[
            "def training_step",
            "def _wrap_model",
            "self.accelerator.backward",
            "self.args.gradient_accumulation_steps",
            "if args.n_gpu > 1",
            "model.zero_grad()"
        ],
        difficulty=3
    ),
    EvalCase(
        question="How does the Trainer class implement custom optimizer and learning rate scheduler creation? Explain the initialization process and supported configurations.",
        expected_files=["trainer.py"],
        expected_concepts=[
            "optimizer initialization",
            "learning rate scheduler",
            "weight decay handling",
            "optimizer parameter groups",
            "AdamW configuration",
            "custom optimizer support"
        ],
        expected_code_refs=[
            "def create_optimizer",
            "def create_scheduler",
            "get_decay_parameter_names",
            "optimizer_grouped_parameters",
            "self.args.learning_rate",
            "optimizer_kwargs"
        ],
        difficulty=3
    )
]

TRANSFORMER_TEST_CASES = [
    *TRANSFORMER_QUANTIZER_BASE_CASES,
    *TRANSFORMER_QUANTIZER_AUTO_CASES,
    *TRANSFORMER_PIPELINE_BASE_TEST_CASES,
    *TRANSFORMER_PIPELINE_TEXT_GENERATION_TEST_CASES,
    *TRANSFORMER_LOGITS_PROCESSOR_TEST_CASES,
    *TRANSFORMER_TRAINER_TEST_CASES,
]