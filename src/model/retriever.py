from typing import List

import MeCab
from sudachipy import tokenizer
from sudachipy import dictionary

from ragatouille import RAGPretrainedModel

from langchain.retrievers.contextual_compression import ContextualCompressionRetriever
from langchain.retrievers import BM25Retriever, EnsembleRetriever


def mecab_tokenizer(text):
    mecab = MeCab.Tagger("-Owakati")
    return mecab.parse(text).split()

def preprocess_func(text: str) -> List[str]:
    tokenizer_obj = dictionary.Dictionary(dict="full").create()
    mode = tokenizer.Tokenizer.SplitMode.A
    tokens = tokenizer_obj.tokenize(text ,mode)
    words = [token.surface() for token in tokens]
    words = list(set(words))
    return words

def create_retriever(
        vector_store,
        topk: int,
        hybrid: bool,
        hybrid_topk: int,
        hybrid_weights: List[float],
        rerank: bool,
        rerank_topk: int
        ):

    def create_rerank_retriever(base_retriever, model="bclavie/JaColBERT"):
        rerank_model = RAGPretrainedModel.from_pretrained(model)
        retriever = ContextualCompressionRetriever(
            base_compressor=rerank_model.as_langchain_document_compressor(k=rerank_topk),
            base_retriever=base_retriever
        )
        return retriever

    def create_hybrid_retriever(vector_store, retriever):
        docs = []
        for id, doc in vector_store.docstore._dict.items():
            docs.append(doc)

        for_hybrid_retriever = BM25Retriever.from_documents(
            documents=docs,
            k=hybrid_topk,
            preprocess_func=preprocess_func
            )
        retriever = EnsembleRetriever(
            retrievers=[retriever, for_hybrid_retriever],
            weights=hybrid_weights
        )
        return retriever

    retriever = vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": topk}
        )
    if hybrid:
        retriever = create_hybrid_retriever(
            vector_store=vector_store,
            retriever=retriever
            )
        if rerank:
            retriever = create_rerank_retriever(
                base_retriever=retriever
            )

    if rerank:
        retriever = create_rerank_retriever(
                base_retriever=retriever
            )
    return retriever