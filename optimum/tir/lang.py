from enum import Enum
from os import PathLike
from pathlib import Path
from typing import NamedTuple, Dict, Optional, Any, List

from huggingface_hub import cached_download, hf_hub_url
from iree.compiler import InputType

from . import _TIR_HUB_USER_AGENT
from tomlkit import load as load_toml


class TirTarget(str, Enum):
    INTERPRETED_CPU = "vmvx"
    COMPILED_CPU = "llvm-cpu"
    COMPILED_GPU = "vulkan"
    COMPILED_CUDA = "cuda"
    COMPILED_ROCM = "rocm"


TirFrontendInfo = NamedTuple("TirFrontendInfo", [("name", str), ("dialect", InputType)])


class TirFrontend(Enum):
    PYTORCH = TirFrontendInfo("pytorch", InputType.TM_TENSOR)
    TENSORFLOW = TirFrontendInfo("tensorflow", InputType.MHLO)
    TFLITE = TirFrontendInfo("tflite", InputType.TOSA)
    JAX = TirFrontendInfo("jax", InputType.XLA)


class TirConfig:

    __slots__ = ("flags", )

    def __init__(self, flags: Optional[List[str]] = None):
        self.flags = flags or []

    def with_debug_flags(self) -> "TirConfig":
        """
        Include the MLIR debugging flags to the compiler invocation
        :return:
        """
        self.flags.insert(0, "mlir-elide-elementattrs-if-larger=1")
        self.flags.insert(0, "mlir-print-ir-before-all")
        return self

    def with_cpu_target(self, target: str = None) -> "TirConfig":
        """
        Define the target CPU LLVM will compile for
        :param target: LLVM cpu target (ex: skylake-avx512, icelake-server, etc.)
        :return:
        """
        if target is None:
            target = "host"

        self.flags.append(f"--iree-llvm-target-cpu-features={target}")
        return self

    def with_gpu_target(self, target_sm: str) -> "TirConfig":
        """
        Define the target GPU SM LLVM will compile for
        :param target_sm: Device capabilities version (SM in Nvidia's vocab)
        :return:
        """
        # TODO: Improve "target_sm" will not speak to many people
        self.flags.append(f"--iree-hal-cuda-llvm-target-arch={target_sm}")
        return self

    def get_compiler_args(self) -> List[str]:
        """
        Return the flags to be forwarded to IREE's compiler
        :return:
        """
        return self.flags

    def get_tuned_parameters_for_device(self, device: TirTarget) -> Optional[Dict[str, Any]]:
        """
        Retrieve tuned parameters for the specified device or a default config if the device doesn't have a tuned
        configuration.
        :param device: The device we are trying to tune for.
        :return:
        """
        raise NotImplementedError()

    def get_tunable_parameters(self, device: TirTarget) -> Optional[Dict[str, Any]]:
        """
        Retrieve which parameters from this configuration can be tuned
        :param device: The device we are trying to tune for.
        :return:
        """
        raise NotImplementedError()

    def register_additional_parameters(self, device: TirTarget, parameter: str, value: Optional[Any], index: int = -1):
        """

        :param device: The device we are trying to tune for.
        :param parameter: The parameter name to append.
        :param value: The value for parameter.
        :param index: Where in the pipeline we should insert this parameter (default -1: at the end).
        :return:
        """
        raise NotImplementedError()


class TirConfigStore:

    @staticmethod
    def from_hub(repo_id: str, filename: str = "tir-config.store", branch: str = "tir") -> "TirConfigStore":
        target_repo_url = hf_hub_url(repo_id=repo_id, filename=filename, revision=branch)
        local_file_path = cached_download(target_repo_url, user_agent=_TIR_HUB_USER_AGENT)

        if local_file_path is not None:
            local_file_path = Path(local_file_path)
            return TirConfigStore.from_file(local_file_path, repo_id)

        raise ValueError(f"Unable to find {filename} at {target_repo_url}.")

    @staticmethod
    def from_file(filepath: PathLike, repo_id: str) -> "TirConfigStore":
        with open(filepath, "r", encoding="utf-8") as store_f:
            store = load_toml(store_f)
            return TirConfigStore(repo_id, store)

    def __init__(self, repo_id: str, store: Dict[str, Dict[str, Any]]):
        self._repo_id = repo_id
        self._store = store

    def __getitem__(self, item):
        return self._store[item]

