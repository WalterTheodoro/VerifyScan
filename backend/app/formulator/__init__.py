"""Análise com IA (ADR-0020): uma chamada ao Claude depois do motor.

A IA lê a mensagem como dado, sugere um nível e escreve tipo, sinais e passos. Quem decide o
nível final é a regra fixa de `scoring/combinacao.py`: a IA pode subir, nunca baixar.
"""
