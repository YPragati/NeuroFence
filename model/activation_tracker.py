import torch


class ActivationTracker:
    """
    Tracks activation statistics from Transformer layers.
    """

    def __init__(self, model):
        self.model = model
        self.activations = {}
        self.hooks = []

    def _create_hook(self, layer_index):
        def hook(module, inputs, output):
            if isinstance(output, tuple):
                output = output[0]

            activation = output.detach().cpu()

            self.activations[layer_index] = {
                "mean": activation.mean().item(),
                "max": activation.max().item(),
                "min": activation.min().item(),
                "std": activation.std().item(),
                "shape": list(activation.shape)
            }

        return hook

    def register_hooks(self):
        """
        Register hooks on all Transformer blocks.
        """

        for index, layer in enumerate(self.model.transformer.h):
            hook = layer.register_forward_hook(
                self._create_hook(index)
            )

            self.hooks.append(hook)

    def remove_hooks(self):
        """
        Remove all registered hooks.
        """

        for hook in self.hooks:
            hook.remove()

        self.hooks.clear()

    def get_activations(self):
        """
        Return collected activation statistics.
        """

        return self.activations