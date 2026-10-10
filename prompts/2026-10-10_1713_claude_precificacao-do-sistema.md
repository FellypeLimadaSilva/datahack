# Sessão: quanto vale e quanto custa implantar o sistema

- **Ferramenta:** Claude Code (Claude Sonnet 5.5)
- **Data:** 2026-10-10
- **Quem usou:** Mauricio Balboa
- **Fase:** Pós-entrega (modelo de negócio e pitch)
- **Objetivo:** estimar o valor de mercado do sistema, o custo de implantação para quem constrói e para a empresa contratante, e preparar a resposta sobre precificação
- **Resultado:** só análise e texto de apoio. Nenhum arquivo do pipeline, do dbt, do Superset ou do chatbot foi alterado. As faixas de preço são estimativas do modelo para o mercado brasileiro, **sem pesquisa de preços ao vivo**, e devem ser tratadas como ordem de grandeza.

## Contexto lido pela IA antes de responder

Memória do projeto (Rota do Diploma, dashboard Superset sobre a camada Gold, chatbot DeepSeek, plano B com planilhas) e o `git status` do repositório. Nenhum arquivo foi aberto nesta sessão para fazer as estimativas.

---

## Prompt 1

> um sistema deste, qual um valor dele em mercado atualmente sobre dados?

**Resposta resumida da IA**

- Descreveu o sistema como pipeline ELT (bronze, silver, gold) + warehouse + dashboard Superset + chatbot + plano B por planilhas, tudo em Docker e com testes.
- Faixas de valor (Brasil):

  | Cenário | Faixa |
  |---|---|
  | Projeto sob encomenda (freelancer ou consultoria pequena) | R$ 15 mil a R$ 40 mil |
  | Consultoria ou software house, com PMO, documentação, treinamento e SLA | R$ 40 mil a R$ 100 mil |
  | Produto adaptado a uma instituição real (integração, LGPD, SSO, hospedagem) | R$ 80 mil a R$ 200 mil |
  | Recorrente (hospedagem, manutenção, evolução, suporte) | R$ 2 mil a R$ 8 mil por mês |

- Base do cálculo: 150 a 400 horas de engenharia de dados, BI e DevOps, a R$ 100–200 por hora. O Superset é open source, então o cliente paga por modelagem, integração e conhecimento, não por licença.
- O que sobe o preço: chatbot em linguagem natural, Gold bem modelada com dicionário, implantação simples por Docker, testes, problema de negócio claro (evasão e conclusão de curso).
- O que baixa: ser protótipo de hackathon, sem monitoramento nem segurança de dados de alunos, chatbot ainda sem teste com a chave real, dados de entrada públicos, cliente poder trocar por Power BI.
- Ressalvas: o valor está mais nos dados e na decisão do que no código; conferir de quem é a propriedade intelectual pelo edital do hackathon; como SaaS por instituição, R$ 1.500 a R$ 8.000 por mês seria plausível, mas exigiria vendas, suporte e multi-tenant que não existem hoje.

**O que foi aproveitado ou corrigido:** nada implementado. Serviu de base para os prompts seguintes.

---

## Prompt 2

> um custo de implementação deste sistema, quanto de custo eu teria, e a empresa contratante teria? uma media

**Resposta resumida da IA**

- **Custo de quem constrói:** caixa de R$ 0 a R$ 1.500 (VPS de demonstração, domínio, API do chat em testes); custo de oportunidade de cerca de R$ 25 mil (250 horas a R$ 100/h); mais 80 a 150 horas para entregar a um cliente (R$ 10 a 20 mil).
- **Empresa contratante, implantação (única vez):** média de R$ 40 mil, faixa de R$ 25 a 80 mil. Distribuição: levantamento 10%, integração com sistemas de origem 25%, modelagem do warehouse 20%, dashboard 15%, chatbot 10%, segurança e LGPD 10%, deploy e treinamento 10%.
- **Empresa contratante, recorrente:** média de R$ 4 mil por mês (servidor R$ 600–1.500, banco gerenciado e backup R$ 400–1.200, monitoramento R$ 200–500, API do chat R$ 50–300, manutenção de 10 a 20 horas R$ 1.500–3.000).
- **Total para a empresa:** cerca de R$ 90 mil no ano 1 e cerca de R$ 50 mil por ano a partir do ano 2. Comparação: Power BI Pro para 50 usuários custa cerca de R$ 45 mil por ano só de licença, e ainda exige modelagem.
- Fatores que mudam o orçamento: LGPD e envio de dados de alunos à API do DeepSeek (fora do Brasil), integração com sistema acadêmico fechado, escala acima de 200 usuários simultâneos.
- Preço sugerido ao cliente final: R$ 40 a 55 mil mais mensalidade, partindo de um custo de entrega de R$ 25 a 35 mil e margem de 30 a 50%.

**O que foi aproveitado ou corrigido:** nada implementado. Os números alimentam a resposta do Prompt 3.

---

## Prompt 3

> se me perguntarem a precificação, oq eu devo responder?

**Resposta resumida da IA**

- Resposta curta para falar: implantação em torno de R$ 40 mil (uma vez) e operação em torno de R$ 4 mil por mês; cerca de R$ 90 mil no primeiro ano e R$ 50 mil por ano depois.
- Justificativa se pedirem: ferramentas open source, sem licença por usuário; o custo está em integração, modelagem e segurança; Power BI para 50 usuários custa algo parecido só de licença.
- Se perguntarem o que o cliente ganha: enxergar onde o aluno trava no caminho até o diploma e agir antes da evasão. Usar as mensalidades da própria instituição na conta de retenção, como simulação, sem inventar taxa de retenção.
- Se perguntarem o custo para o desenvolvedor: falar só do tempo (cerca de 250 horas) e de caixa quase zero; não revelar margem.
- O que dizer: "é uma estimativa de mercado, o valor final depende do levantamento"; dar faixa (R$ 30 a 50 mil) se o interlocutor decide.
- O que evitar: dizer que é de graça por ser Superset; prometer retorno financeiro específico.
- Sobre o chatbot e a LGPD: ser franco que hoje usa a API do DeepSeek e que, em produção com dados de alunos, a recomendação é modelo hospedado no Brasil ou local, o que adiciona custo recorrente.
- Para banca de hackathon: o foco costuma ser viabilidade e impacto; usar a resposta curta, citar que roda em Docker e é replicável, e voltar ao impacto.

**O que foi aproveitado ou corrigido:** nada implementado. Ficou como roteiro de resposta para o pitch.

---

## Prompt 4

> faça uma documentação sobre todos meus prompts em .md desta janela de contexto

**Resposta resumida da IA**

- Criou este arquivo seguindo o padrão da pasta (`AAAA-MM-DD_HHMM_ferramenta_tema.md`) e o formato do arquivo `2026-10-10_1713_claude_integracao-deepseek.md`.
- Adicionou uma linha no índice `prompts/README.md`.

**O que foi aproveitado ou corrigido:** este próprio documento.

---

## Pontos a conferir antes de usar os números

1. Os valores são **estimativas sem fonte**: conferir com propostas reais, tabelas de salário e preços atuais de nuvem antes de apresentar como dado.
2. Confirmar no edital do hackathon quem detém a propriedade intelectual do projeto.
3. Decidir o modelo de LLM para produção (a questão LGPD do DeepSeek pesa no custo recorrente).
4. O chatbot ainda precisa de teste com a chave real, o que afeta o argumento de valor.
