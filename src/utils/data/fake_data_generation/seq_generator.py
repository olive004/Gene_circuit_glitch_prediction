from functools import partial
from typing import List
import numpy as np
import jax.numpy as jnp
import jax.random as jr
import random
from Bio.Seq import Seq

from src.utils.results.writer import DataWriter
from src.utils.misc.helper import next_wrapper
from src.utils.misc.numerical import generate_mixed_binary
from src.utils.misc.string_handling import ordered_merge, list_to_str


class SeqGenerator():

    SEQ_POOL = {}

    def __init__(self, data_writer: DataWriter, seed=0) -> None:
        self.stype = None
        self.data_writer = data_writer

        np.random.seed(seed)

    @staticmethod
    def generate_mutated_template(template: str, mutate_prop, mutation_pool):
        mutate_idxs = np.random.randint(
            len(template), size=int(len(template)*mutate_prop))
        template = list(template)
        for idx in mutate_idxs:
            template[idx] = np.random.choice(
                list(mutation_pool.keys()), p=list(mutation_pool.values()))
        template = ''.join(template)
        return template

    @staticmethod
    def generate_str_from_probdict(str_prob_dict: dict, slength) -> str:
        population = list(str_prob_dict.keys())
        probabilities = list(str_prob_dict.values())
        return ''.join(random.choices(population, probabilities, k=slength))

    @staticmethod
    def generate_str_from_probdict_batch(str_prob_dict: dict, shape) -> str:
        population = np.array(list(str_prob_dict.keys()))
        probabilities = np.array(list(str_prob_dict.values()))
        str_choices = np.random.choice(population, size=shape, p=probabilities)
        return [''.join(s) for s in str_choices]

    def get_sequence_complement(self, seq):
        if self.stype == 'RNA':
            return str(Seq(seq).complement_rna())
        else:
            return str(Seq(seq).complement())

class NucleotideGenerator(SeqGenerator):

    def __init__(self, data_writer, **kwargs) -> None:
        super().__init__(data_writer, **kwargs)

    def convert_symbolic_complement(self, real_seq, symbolic_complement):
        comp_seq = self.get_sequence_complement(real_seq)
        return list_to_str(ordered_merge(real_seq, comp_seq, symbolic_complement))

    def generate_split_template(self, template: str, count) -> list:
        """ Example: AAACCCUUU -> CCCCCOOOOO + OOOOOCCCCC -> UUUGGCUUU + AAACCGAAA 
        C = Complement, O = Original """
        assert count < len(template), \
            f"Desired sequence length {len(template)} too short to accomodate {count} samples."
        template_complement = self.get_sequence_complement(template)
        fold = max(int(len(template) / count), 1)

        seqs = []  # could preallocate
        for i in range(0, len(template), fold):
            complement = template_complement[i:(i+fold)]
            new_seq = template[:i] + complement + template[(i+fold):]
            seqs.append(new_seq)
        return seqs[:count]

    def generate_mixed_template(self, template: str, count) -> list:
        """ Example: AAACCCUUU -> CCOOCCOOCC + OOCCOOCCOO -> AAACCCUUU + AAACCCUUU
        C = Complement, O = Original """
        # TODO: Generate proper permutations or arpeggiations,
        # rank by mixedness and similarity. Can use list(permutations())
        # and ranking function in future.

        symbolic_complements = generate_mixed_binary(
            len(template), count, zeros_to_ones=False)
        seq_permutations = [None] * count
        for i, symb in enumerate(symbolic_complements):
            seq_permutations[i] = self.convert_symbolic_complement(
                template, symb)
        return seq_permutations

    def generate_circuits(self, iter_count=1, name='toy_mRNA_circuit', circuit_paths=None, **circuit_kwargs) -> List[dict]:
        if circuit_paths is None:
            circuit_paths = []
        for i in range(iter_count):
            circuit_kwargs['name'] = name + '_' + str(i)
            circuit_path = self.generate_circuit(**circuit_kwargs)
            circuit_paths.append(circuit_path)
        return circuit_paths

    def generate_circuit(self, num_components=3, slength=20, protocol="random",
                         name='toy_mRNA_circuit',
                         out_type='fasta',
                         proportion_to_mutate=0, template=None) -> dict:
        """ Protocol can be 
        'random': Random sequence generated with weighted characters
        'template_mix': A template sequence is interleaved with complementary characters
        'template_mutate': A template sequence is mutated according to weighted characters
        'template_split': Parts of a template sequence are made complementary
        """

        if template is None:
            template = self.generate_str_from_probdict(self.SEQ_POOL, slength)
        # template = 'CGCGCGCGCGCGCGCGCGCGCGCCGCGCG'  # Very strong interactions
        # template = 'CUUCAAUUCCUGAAGAGGCGGUUGG'  # Very weak interactions
        if protocol == "template_mutate":
            seq_generator = partial(self.generate_mutated_template,
                                    template=template,
                                    mutate_prop=proportion_to_mutate,
                                    mutation_pool=self.SEQ_POOL)
        elif protocol == "template_split":
            sequences = self.generate_split_template(template, num_components)
            seq_generator = partial(next_wrapper, generator=iter(sequences))
        elif protocol == "template_mix":
            sequences = self.generate_mixed_template(template, num_components)
            seq_generator = partial(next_wrapper, generator=iter(sequences))
        elif protocol == "random":
            seq_generator = partial(self.generate_str_from_probdict,
                                    str_prob_dict=self.SEQ_POOL, slength=slength)
        else:
            raise NotImplementedError

        out_path = self.data_writer.output(out_name=name, out_type=out_type,
                                           seq_generator=seq_generator, stype=self.stype,
                                           count=num_components, return_path=True,
                                           subfolder='circuits')
        return {'data_path': out_path}

    def generate_circuits_batch(self, num_circuits, slength, num_components: int,
                                protocol="random",
                                name='toy_mRNA_circuit',
                                out_type='fasta',
                                proportion_to_mutate=0, template=None) -> List[dict]:
        shape = (num_circuits, slength)
        paths = [None] * num_circuits
        templates = self.generate_str_from_probdict_batch(
            str_prob_dict=self.SEQ_POOL, shape=shape)
        if protocol == "random":
            all_templates = [None] * num_components
            all_templates[0] = templates
            for n in range(1, num_components):
                all_templates[n] = self.generate_str_from_probdict_batch(
                    str_prob_dict=self.SEQ_POOL, shape=shape)
            all_templates = np.array(all_templates)
            for i in range(num_circuits):
                paths[i] = {'data_path': self.data_writer.output(out_name=name + '_' + str(i), out_type=out_type,
                                                   seq_generator=None, stype=self.stype,
                                                   data=all_templates[:, i],
                                                   count=num_components, return_path=True,
                                                   byseq=True,
                                                   subfolder='circuits')}
        else:
            for i in range(num_circuits):
                t = template if template is not None else templates[i]
                paths[i] = self.generate_circuit(
                    name=name + '_' + str(i),
                    num_components=num_components, slength=slength,
                    protocol=protocol,
                    out_type=out_type,
                    proportion_to_mutate=proportion_to_mutate,
                    template=t
                )
        return paths


class RNAGenerator(NucleotideGenerator):

    SEQ_POOL = {
        'A': 0.254,
        'C': 0.254,
        'G': 0.246,
        'U': 0.246
    }

    def __init__(self, data_writer, **kwargs) -> None:
        super().__init__(data_writer, **kwargs)
        self.stype = "RNA"


class DNAGenerator(NucleotideGenerator):

    SEQ_POOL = {
        'A': 0.254,
        'C': 0.254,
        'G': 0.246,
        'T': 0.246
    }

    def __init__(self, data_writer, **kwargs) -> None:
        super().__init__(data_writer, **kwargs)
        self.stype = "DNA"


def main():
    # Testing
    template = 'ACTGTGTGCCCCTAAACCGCGCT'
    count = 10
    seq_permutations = DNAGenerator().generate_mixed_template(template, count)
    assert len(seq_permutations) == count, 'Wrong sequence length.'
    print(seq_permutations)
