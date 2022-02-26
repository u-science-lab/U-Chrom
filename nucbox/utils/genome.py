
class GenomeRange(object):
    SUPER_MAX = 100000000000000000000

    def __init__(self, chr, start=0, end=SUPER_MAX):
        self.chr = chr
        if (start is not None) and (end is not None):
            self.start = int(start)
            self.end = int(end)
            assert self.end > self.start >= 0

    @staticmethod
    def parse_text(text, valid_chr_names=None):
        if ":" in text:
            assert "-" in text
            tp1 = text.split(":")
            chr = tp1[0]
            start, end = tp1[1].split("-")
            gr = GenomeRange(chr, start, end)
        else:
            gr = GenomeRange(text)
        if valid_chr_names is not None:
            assert gr.chr in valid_chr_names
        return gr

    def __str__(self):
        if (self.start == 0) and (self.end == self.SUPER_MAX):
            return self.chr
        else:
            return f"{self.chr}:{self.start}-{self.end}"

    def __repr__(self):
        return f"GenomeRange({str(self)})"

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        return str(self) == str(other)

    def __gt__(self, other):
        return (self.start > other.start) and (self.end > other.end)

    def __lt__(self, other):
        return (self.start < other.start) and (self.end < other.end)
