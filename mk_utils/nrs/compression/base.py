class CompressionBase:
    def decompress(self, chunk, type_):
        raise NotImplementedError(f"Abstract Class")

    def compress(self, chunk, type_):
        raise NotImplementedError(f"Abstract Class")
