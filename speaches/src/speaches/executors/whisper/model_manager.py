from __future__ import annotations

from collections import OrderedDict
import logging
import threading
from typing import TYPE_CHECKING

from faster_whisper import WhisperModel

from speaches.model_manager import SelfDisposingModel

if TYPE_CHECKING:
    from speaches.config import (
        WhisperConfig,
    )

logger = logging.getLogger(__name__)


# TODO: enable concurrent model downloads


class WhisperModelManager:
    def __init__(self, whisper_config: WhisperConfig) -> None:
        self.whisper_config = whisper_config
        self.loaded_models: OrderedDict[str, SelfDisposingModel[WhisperModel]] = OrderedDict()
        self._lock = threading.Lock()

    def _load_fn(self, model_id: str) -> WhisperModel:
        return WhisperModel(
            model_id,
            device=self.whisper_config.inference_device,
            device_index=self.whisper_config.device_index,
            compute_type=self.whisper_config.compute_type,
            cpu_threads=self.whisper_config.cpu_threads,
            num_workers=self.whisper_config.num_workers,
        )

    def _handle_model_unloaded(self, model_id: str) -> None:
        with self._lock:
            if model_id in self.loaded_models:
                del self.loaded_models[model_id]

    def unload_model(self, model_id: str) -> None:
        with self._lock:
            model = self.loaded_models.get(model_id)
            if model is None:
                raise KeyError(f"Model {model_id} not found")
            # WARN: ~300 MB of memory will still be held by the model. See https://github.com/SYSTRAN/faster-whisper/issues/992
            self.loaded_models[model_id].unload()

    def load_model(self, model_id: str) -> SelfDisposingModel[WhisperModel]:
        logger.debug(f"Loading model {model_id}")
        with self._lock:
            logger.debug("Acquired lock")
            if model_id in self.loaded_models:
                logger.debug(f"{model_id} model already loaded")
                return self.loaded_models[model_id]
            
            # 检查模型是否存在，如果不存在则自动下载
            try:
                from speaches.executors.whisper.utils import model_registry
                # 尝试获取模型文件，如果失败则自动下载
                try:
                    model_registry.get_model_files(model_id)
                    logger.debug(f"Model {model_id} files found locally")
                except Exception:
                    logger.info(f"Model {model_id} not found locally, attempting auto-download...")
                    try:
                        was_downloaded = model_registry.download_model_files_if_not_exist(model_id)
                        if was_downloaded:
                            logger.info(f"✅ Model {model_id} downloaded successfully")
                        else:
                            logger.info(f"Model {model_id} already exists after check")
                    except Exception as download_error:
                        logger.error(f"❌ Failed to download model {model_id}: {download_error}")
                        raise download_error
            except Exception as e:
                logger.error(f"Model preparation failed for {model_id}: {e}")
                raise e
                
            self.loaded_models[model_id] = SelfDisposingModel[WhisperModel](
                model_id,
                load_fn=lambda: self._load_fn(model_id),
                ttl=self.whisper_config.ttl,
                model_unloaded_callback=self._handle_model_unloaded,
            )
            return self.loaded_models[model_id]
