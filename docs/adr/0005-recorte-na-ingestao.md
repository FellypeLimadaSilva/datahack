# ADR 0005 — Recorte de escopo na ingestão, ELT como padrão

- **Status:** aceito · **Data:** 2026-10-10

## Contexto
Os arquivos nacionais do Censo e da Trajetória têm 40 vezes o volume de Mato Grosso, e o desafio é
só sobre MT.

## Decisão
ELT como padrão. Antes de gravar, só `transforms` declarativas de recorte e forma (`filter`,
`rename`, `select_columns`, `drop_columns`), nunca regra de negócio nem alteração de valor.

## Consequências
+ 37 a 46 vezes menos disco e cargas 2 vezes mais rápidas nas máquinas do laboratório.
− Linhas de outras UFs não chegam à Bronze; para voltar ao nacional, basta remover o `filter` e recarregar.
