from collections import OrderedDict
import logging
import threading

from kokoro_onnx import Kokoro
from onnxruntime import InferenceSession, get_available_providers

from speaches.config import OrtOptions
from speaches.executors.kokoro.utils import model_registry
from speaches.model_manager import SelfDisposingModel

logger = logging.getLogger(__name__)


class KokoroModelManager:
    def __init__(self, ttl: int, ort_opts: OrtOptions) -> None:
        self.ttl = ttl
        self.ort_opts = ort_opts
        self.loaded_models: OrderedDict[str, SelfDisposingModel[Kokoro]] = OrderedDict()
        self._lock = threading.Lock()

    def _load_fn(self, model_id: str) -> Kokoro:
        model_files = model_registry.get_model_files(model_id)
        # NOTE: `get_available_providers` is an unknown symbol (on MacOS at least)
        available_providers: list[str] = get_available_providers()
        logger.debug(f"Available ONNX Runtime providers: {available_providers}")
        available_providers = [
            provider for provider in available_providers if provider not in self.ort_opts.exclude_providers
        ]
        available_providers = sorted(
            available_providers,
            key=lambda x: self.ort_opts.provider_priority.get(x, 0),
            reverse=True,
        )
        available_providers_with_opts = [
            (provider, self.ort_opts.provider_opts.get(provider, {})) for provider in available_providers
        ]
        logger.debug(f"Using ONNX Runtime providers: {available_providers_with_opts}")
        inf_sess = InferenceSession(model_files.model, providers=available_providers_with_opts)
        return Kokoro.from_session(inf_sess, str(model_files.voices))

    def _handle_model_unloaded(self, model_id: str) -> None:
        with self._lock:
            if model_id in self.loaded_models:
                del self.loaded_models[model_id]

    def unload_model(self, model_id: str) -> None:
        with self._lock:
            model = self.loaded_models.get(model_id)
            if model is None:
                raise KeyError(f"Model {model_id} not found")
            self.loaded_models[model_id].unload()

    def load_model(self, model_id: str) -> SelfDisposingModel[Kokoro]:
        with self._lock:
            if model_id in self.loaded_models:
                logger.debug(f"{model_id} model already loaded")
                return self.loaded_models[model_id]
            
            # 检查模型是否存在，如果不存在则自动下载
            try:
                # 尝试获取模型文件，如果失败则自动下载
                try:
                    model_registry.get_model_files(model_id)
                    logger.debug(f"Kokoro model {model_id} files found locally")
                except Exception:
                    logger.info(f"Kokoro model {model_id} not found locally, attempting auto-download...")
                    try:
                        was_downloaded = model_registry.download_model_files_if_not_exist(model_id)
                        if was_downloaded:
                            logger.info(f"✅ Kokoro model {model_id} downloaded successfully")
                        else:
                            logger.info(f"Kokoro model {model_id} already exists after check")
                    except Exception as download_error:
                        logger.error(f"❌ Failed to download Kokoro model {model_id}: {download_error}")
                        raise download_error
            except Exception as e:
                logger.error(f"Kokoro model preparation failed for {model_id}: {e}")
                raise e
                
            self.loaded_models[model_id] = SelfDisposingModel[Kokoro](
                model_id,
                load_fn=lambda: self._load_fn(model_id),
                ttl=self.ttl,
                model_unloaded_callback=self._handle_model_unloaded,
            )
            return self.loaded_models[model_id]
