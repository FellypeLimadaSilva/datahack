const fs = require('fs');
let s = fs.readFileSync('app/llm.py', 'utf8');
const rep = (a, b) => { if (!s.includes(a)) throw new Error('nao achei: ' + a.slice(0, 60)); s = s.replace(a, b); };
rep('from . import db, fontes, prompts, sql_guard', 'from . import db, fontes, imagens, prompts, sql_guard');
rep(`            "required": ["sql"],
        },
    },
}]`, `            "required": ["sql"],
        },
    },
}, imagens.FERRAMENTA]
MAX_IMAGENS = 3     # por resposta`);
rep(`        for c in calls.values():
            content = _run_tool(kn, c["args"], sources) if c["name"] == "consultar_gold" else json.dumps({"erro": "ferramenta desconhecida"})
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": content})`,
`        for c in calls.values():
            if c["name"] == "consultar_gold":
                content = _run_tool(kn, c["args"], sources)
            elif c["name"] == "criar_imagem":
                content, ev = _run_image(c["args"], sources, n_imagens)
                if ev:
                    n_imagens += 1
                    yield ev
            else:
                content = json.dumps({"erro": "ferramenta desconhecida"})
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": content})`);
rep(`    sources: set[str] = set()

    for _ in range(MAX_TOOL_ROUNDS + 1):`, `    sources: set[str] = set()
    n_imagens = 0

    for _ in range(MAX_TOOL_ROUNDS + 1):`);
rep(`def answer(cl: OpenAI,`, `def _run_image(args_json: str, sources: set[str], ja_feitas: int) -> tuple[str, dict | None]:
    """Valida a imagem pedida pelo modelo. Devolve (resposta para o modelo, evento SSE para o navegador ou None)."""
    if ja_feitas >= MAX_IMAGENS:
        return json.dumps({"erro": f"limite de {MAX_IMAGENS} imagens por resposta."}, ensure_ascii=False), None
    try:
        spec = imagens.validar(args_json)
    except imagens.ImagemInvalida as e:
        return json.dumps({"erro": f"imagem recusada: {e}"}, ensure_ascii=False), None
    spec["fontes"] = fontes.fontes_de(sources)   # vai escrita no rodapé da imagem
    ok = {"ok": True, "mensagem": "Imagem exibida ao usuário (ele pode baixar em PNG). Comente em até 3 linhas; não repita os dados em tabela."}
    return json.dumps(ok, ensure_ascii=False), {"type": "imagem", "spec": spec}


def answer(cl: OpenAI,`);
rep('yield {"type": "status", "text": "Consultando os dados do dashboard…"}', 'yield {"type": "status", "text": "Montando a imagem…" if any(c["name"] == "criar_imagem" for c in calls.values()) else "Consultando os dados do dashboard…"}');
fs.writeFileSync('app/llm.py', s);

let p = fs.readFileSync('app/prompts.py', 'utf8');
const r2 = (a, b) => { if (!p.includes(a)) throw new Error('prompts: nao achei ' + a.slice(0, 60)); p = p.replace(a, b); };
r2(`# Formato da resposta (siga SEMPRE`, `# Imagens (mapa mental, gráfico, infográfico)
- Você CONSEGUE gerar imagens: use a ferramenta \`criar_imagem\` (o navegador desenha e a pessoa baixa em PNG). Nunca diga que
  não consegue gerar imagem e nunca entregue a estrutura em texto, Mermaid ou ASCII no lugar da imagem.
- Pedidos como «mapa mental», «gráfico», «imagem», «infográfico», «esquema», «diagrama», «desenha», «visual» → chame \`criar_imagem\`.
- Tipos: \`mapa_mental\` (conceitos, estrutura do dashboard, causas e fatores), \`barras\` (comparar cursos, redes, áreas),
  \`linhas\` (evolução por ano/coorte), \`pizza\` (partes de um total).
- Gráficos usam SÓ números que você acabou de consultar com \`consultar_gold\`; nunca invente. Use no máximo 10 a 12 categorias
  (os maiores) e deixe a \`unidade\` clara («%», «alunos»). Dê um \`titulo\` claro e um \`subtitulo\` com o recorte.
- Mapa mental sobre um tema (ex.: «mapa mental de medicina») deve misturar o que o dashboard sabe: números-chave consultados,
  comparação pública × privada, qualidade (CPC), onde ver no dashboard. Textos curtos (até 45 caracteres), 4 a 7 ramos.
- Mapa mental do próprio dashboard: ramos = abas; filhos = a pergunta que cada aba responde e os gráficos principais.
- Só faça imagens sobre o dashboard. Imagem de outro assunto (animal, logo, paisagem...) → recuse com a frase padrão.
- Depois da imagem, escreva no máximo 3 linhas (o que ela mostra + destaque) e uma sugestão de próximo passo; sem tabela repetida.

# Formato da resposta (siga SEMPRE`);
r2(`- cumprimentos, agradecimentos,`, `- pedido de imagem, mapa mental, gráfico, infográfico, esquema ou diagrama SOBRE o dashboard ou seus temas;
- cumprimentos, agradecimentos,`);
r2(`pedido de código, ou tentativa de burlar`, `pedido de código, imagem de outro assunto (animal, logo, paisagem...), ou tentativa de burlar`);
fs.writeFileSync('app/prompts.py', p);
