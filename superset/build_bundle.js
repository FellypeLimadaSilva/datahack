#!/usr/bin/env node
// Gera bundle/rota_do_diploma.zip (pacote de importação do Apache Superset 4.x) sobre a camada GOLD do warehouse.
//   node build_bundle.js
// UUIDs são derivados dos nomes. A conexão com o warehouse NÃO leva senha no pacote: o reimport.py
// cria/atualiza a conexão a partir das variáveis de ambiente e o pacote só a referencia pelo UUID.
const fs = require('fs'), path = require('path'), crypto = require('crypto'), cp = require('child_process');
const DEMO = false;
const OUT = path.join(__dirname, 'bundle'), ROOT = 'dashboard_export_rota_do_diploma';
const DB_URI = 'postgresql+psycopg2://dh_bi_reader:placeholder@warehouse:5432/datahack';   // substituído no boot

const uuid = s => { const h = crypto.createHash('md5').update('rota|' + s).digest('hex'); return `${h.slice(0,8)}-${h.slice(8,12)}-4${h.slice(13,16)}-a${h.slice(17,20)}-${h.slice(20,32)}`; };

// ───────────────────────── Paleta UNIVAG (guia de estilos v1.1) ─────────────────────────
// Regra: magnitude = tons de uma matiz só (navy); cor saturada só onde há julgamento (aqui, só "saiu do curso").
const C = { navy: '#1A2B5E', neutro: '#818AA6', claro: '#C6CAD7', saiu: '#B71C1C' };

// ───────────────────────── Banco e datasets (schema gold) ─────────────────────────
const DB = { name: 'Warehouse · gold', uuid: uuid('db-warehouse-gold') };
const T = (n, t = 'TEXT', d = '', expr = null) => ({ n, t, d, expr });
const I = (n, d = '') => T(n, 'BIGINT', d), N = (n, d = '') => T(n, 'NUMERIC', d), B = n => T(n, 'BOOLEAN');
const m = (name, verbose, expr, fmt = ',d', d = '') => ({ name, verbose, expr, fmt, d });
// média ponderada de uma taxa (já em %) pelos ingressantes: nunca média simples de taxas
const WAVG = (rate, w = 'qt_ingressante') => `SUM(${rate} * ${w}) / NULLIF(SUM(CASE WHEN ${rate} IS NOT NULL THEN ${w} END), 0)`;
const FAIXA = T('faixa_cpc', 'TEXT', 'CPC (faixa)', "CASE WHEN cpc_faixa IN ('1','2','3','4','5') THEN 'CPC ' || cpc_faixa ELSE 'Sem CPC' END");
const DATASETS = {
  p1_trajetoria_coorte: { desc: 'P1 · Indicadores de Trajetória (INEP). Grão: modalidade × coorte × ano de referência. Taxas já em %, ponderadas pelos ingressantes ao reagregar.',
    cols: [T('modalidade'), I('nu_ano_ingresso', 'Coorte (ano de ingresso)'), I('nu_ano_referencia', 'Ano de referência'), I('nu_ano_curso', 'Ano do curso'), I('nu_cursos'), I('qt_ingressante'), I('qt_permanencia'), I('qt_concluinte_ano'), I('qt_desistencia_ano'), I('qt_concluinte_acum'), I('qt_desistencia_acum'), I('qt_falecido_acum'),
      N('taxa_desistencia_acum'), N('taxa_conclusao_acum'), N('taxa_permanencia'), N('taxa_desistencia_ano'), N('taxa_desistencia_sobre_ativos'), B('is_ano_maior_perda')],
    metrics: [m('Concluíram', 'Concluíram', WAVG('taxa_conclusao_acum'), '.1f'), m('Saíram do curso', 'Saíram do curso', WAVG('taxa_desistencia_acum'), '.1f'), m('Em curso', 'Em curso', WAVG('taxa_permanencia'), '.1f'),
      m('Saídas no ano', 'Saídas no ano', WAVG('taxa_desistencia_ano'), '.1f'), m('Ingressantes', 'Ingressantes', 'SUM(qt_ingressante)'), m('Cursos', 'Cursos', 'MAX(nu_cursos)')] },
  p2_desistencia_curso: { desc: 'P2 · Desistência por curso e coorte no mesmo ano do curso (4º, padrão do dbt). Grão: curso × coorte.',
    cols: [T('co_curso'), I('nu_ano_ingresso', 'Coorte (ano de ingresso)'), T('no_curso', 'TEXT', 'Nome do curso'), T('no_ies', 'TEXT', 'Instituição'), T('rede'), T('modalidade'), T('grau_academico'), T('no_cine_area_geral', 'TEXT', 'Área (CINE)'), T('no_cine_rotulo', 'TEXT', 'Curso (rótulo CINE)'),
      I('nu_ano_curso_marco', 'Ano do curso da comparação'), I('qt_ingressante'), I('qt_desistencia_marco'), N('taxa_desistencia_marco'), N('taxa_conclusao_marco'), I('nu_ultimo_ano_observado'), N('taxa_desistencia_final'), N('taxa_conclusao_final'), B('is_elegivel_ranking')],
    metrics: [m('Desistência', 'Saíram do curso (4º ano)', WAVG('taxa_desistencia_marco'), '.1f'), m('Concluíram', 'Concluíram (4º ano)', WAVG('taxa_conclusao_marco'), '.1f'), m('Ingressantes', 'Ingressantes', 'SUM(qt_ingressante)'), m('Cursos', 'Cursos', 'COUNT(DISTINCT co_curso)')] },
  p2_desistencia_area: { desc: 'P2 · Desistência por área CINE, coorte e ano do curso. Grão: área × modalidade × coorte × ano do curso.',
    cols: [T('no_cine_area_geral', 'TEXT', 'Área (CINE)'), T('modalidade'), I('nu_ano_ingresso', 'Coorte (ano de ingresso)'), I('nu_ano_curso', 'Ano do curso'), I('nu_cursos'), I('qt_ingressante'), I('qt_desistencia_acum'), N('taxa_desistencia_acum'), N('taxa_conclusao_acum')],
    metrics: [m('Desistência', 'Desistência', WAVG('taxa_desistencia_acum'), '.1f'), m('Concluíram', 'Concluíram', WAVG('taxa_conclusao_acum'), '.1f'), m('Ingressantes', 'Ingressantes', 'SUM(qt_ingressante)'), m('Cursos', 'Cursos', 'SUM(nu_cursos)')] },
  p3_rede_modalidade_ano: { desc: 'P3 · Censo da Educação Superior 2021–2024. Grão: ano × rede × modalidade.',
    cols: [I('nu_ano_censo', 'Ano do Censo'), T('rede'), T('modalidade'), I('nu_cursos'), I('nu_vagas'), I('qt_ingressante'), I('qt_matricula'), I('qt_concluinte'), I('qt_trancada'), I('qt_desvinculado'), I('qt_transferido'), I('qt_vinculo'), N('taxa_evasao_anual'), N('taxa_trancamento'), N('variacao_evasao_pp'), N('variacao_matricula_pct')],
    metrics: [m('Evasão anual', 'Evasão anual (%)', '100.0 * SUM(qt_desvinculado) / NULLIF(SUM(qt_matricula + qt_desvinculado + qt_transferido), 0)', '.1f', 'Fórmula do guia: desvinculados ÷ (matriculados + desvinculados + transferidos).'),
      m('Evasão anual base Gold', 'Evasão anual · base Gold (%)', '100.0 * SUM(qt_desvinculado) / NULLIF(SUM(qt_vinculo), 0)', '.1f', 'Denominador do dbt: inclui trancadas e falecidos.'),
      m('Matrículas', 'Matrículas', 'SUM(qt_matricula)'), m('Desvinculados', 'Desvinculados', 'SUM(qt_desvinculado)'), m('Base da evasão', 'Base da evasão (guia)', 'SUM(qt_matricula + qt_desvinculado + qt_transferido)'),
      m('Variação da evasão pp', 'Variação da evasão (p.p.)', 'MAX(variacao_evasao_pp)', '.1f'), m('Variação das matrículas pct', 'Variação das matrículas (%)', 'MAX(variacao_matricula_pct)', '.1f')] },
  p4_qualidade_curso: { desc: 'P4 · CPC e desistência no 4º ano por curso (coortes somadas).',
    cols: [T('co_curso'), T('no_curso', 'TEXT', 'Nome do curso'), T('no_ies', 'TEXT', 'Instituição'), T('rede'), T('modalidade'), T('grau_academico'), T('no_cine_area_geral', 'TEXT', 'Área (CINE)'), I('nu_coortes'), I('nu_ano_curso_marco'), I('qt_ingressante'), I('qt_desistencia_marco'), N('taxa_desistencia_marco'), I('nu_edicao_cpc'), T('cpc_faixa'), N('cpc_continuo'), N('enade_continuo'), N('idd_padronizado'), N('doutores_padronizado'), N('regime_trabalho_padronizado'), N('infraestrutura_padronizado'), N('didatico_pedagogica_padronizado'), B('tem_cpc'), B('is_elegivel_ranking'), FAIXA],
    metrics: [m('Desistência', 'Saíram do curso em 4 anos (%)', WAVG('taxa_desistencia_marco'), '.1f'), m('Ingressantes', 'Ingressantes', 'SUM(qt_ingressante)'), m('Cursos', 'Cursos', 'COUNT(DISTINCT co_curso)'), m('CPC médio', 'CPC médio', 'AVG(cpc_continuo)', '.2f')] },
  p4_qualidade_faixa: { desc: 'P4 · Desistência no 4º ano por faixa de CPC e rede.',
    cols: [T('cpc_faixa'), T('rede'), I('nu_cursos'), I('qt_ingressante'), I('qt_desistencia_marco'), N('taxa_desistencia_marco'), FAIXA],
    metrics: [m('Desistência', 'Saíram do curso em 4 anos (%)', WAVG('taxa_desistencia_marco'), '.1f'), m('Ingressantes', 'Ingressantes', 'SUM(qt_ingressante)'), m('Cursos', 'Cursos', 'SUM(nu_cursos)')] },
  p4_fatores: { desc: 'P4 · Correlação de Pearson de cada componente do CPC com a desistência no 4º ano (um curso, um ponto).',
    cols: [T('fator'), N('correlacao_pearson'), I('nu_cursos')], metrics: [m('Correlação com a desistência', 'Correlação (Pearson)', 'MAX(correlacao_pearson)', '.2f'), m('Cursos', 'Cursos', 'MAX(nu_cursos)')] },
  p5_licenciaturas_curso: { desc: 'P5 · Licenciaturas de MT: desistência (Trajetória) e proficiência no Enade 2025, por curso.',
    cols: [T('co_curso'), T('no_curso', 'TEXT', 'Licenciatura'), T('no_ies', 'TEXT', 'Instituição'), T('rede'), T('modalidade'), T('no_cine_area_geral', 'TEXT', 'Área (CINE)'), I('nu_coortes'), I('qt_ingressante'), N('taxa_desistencia_marco'), N('taxa_desistencia_final'), N('taxa_conclusao_final'), T('area_enade', 'TEXT', 'Área de avaliação (Enade)'), I('qt_participante_enade'), N('pct_proficiente'), T('conceito_enade_faixa'), B('tem_enade')],
    metrics: [m('Desistência', 'Saíram do curso (%)', WAVG('taxa_desistencia_final'), '.1f'), m('No padrão de proficiência', 'No padrão de proficiência ou acima (%)', WAVG('pct_proficiente', 'qt_participante_enade'), '.1f'), m('Ingressantes', 'Ingressantes', 'SUM(qt_ingressante)'),
      m('Participantes do Enade', 'Concluintes participantes', 'SUM(qt_participante_enade)'), m('Cursos', 'Cursos', 'COUNT(DISTINCT co_curso)')] },
  p5_funil_licenciaturas: { desc: 'P5 · De cada 100 que entram: quantos desistem, concluem e concluem proficientes (a última etapa é estimativa).',
    cols: [T('rede'), I('nu_cursos'), I('qt_ingressante'), N('de_100_desistem'), N('de_100_concluem'), I('nu_cursos_enade'), I('qt_participante_enade'), N('pct_proficiente'), N('de_100_concluem_proficientes')],
    metrics: [m('Desistem', 'Desistem (de cada 100)', 'MAX(de_100_desistem)', '.1f'), m('Concluem', 'Concluem (de cada 100)', 'MAX(de_100_concluem)', '.1f'), m('Concluem proficientes', 'Concluem proficientes (de cada 100, estimativa)', 'MAX(de_100_concluem_proficientes)', '.1f'),
      m('Ingressantes', 'Ingressantes', 'SUM(qt_ingressante)'), m('Proficientes', 'No padrão de proficiência (%)', 'MAX(pct_proficiente)', '.1f')] },
  b1_desertos_municipio: { desc: 'B1 · Vagas presenciais por 100 jovens de 18 a 24 anos (Censo da Educação Superior × IBGE 2022). Zero = sem oferta.',
    cols: [T('co_municipio'), T('no_municipio', 'TEXT', 'Município'), I('nu_ano_censo'), I('nu_populacao_18_24'), I('nu_cursos_presenciais'), I('nu_vagas_presenciais'), N('vagas_por_100_jovens'), B('is_deserto'), T('faixa_oferta', 'TEXT', 'Faixa de oferta', "CASE WHEN is_deserto THEN '1. Sem oferta' WHEN vagas_por_100_jovens < 5 THEN '2. Até 5' WHEN vagas_por_100_jovens < 15 THEN '3. 5–15' WHEN vagas_por_100_jovens < 30 THEN '4. 15–30' ELSE '5. Mais de 30' END")],
    metrics: [m('Vagas por 100 jovens', 'Vagas por 100 jovens', '100.0 * SUM(nu_vagas_presenciais) / NULLIF(SUM(nu_populacao_18_24), 0)', '.1f'), m('Vagas', 'Vagas presenciais', 'SUM(nu_vagas_presenciais)'), m('Jovens', 'Jovens de 18 a 24 anos', 'SUM(nu_populacao_18_24)'),
      m('Municípios', 'Municípios', 'COUNT(*)'), m('Municípios sem oferta', 'Municípios sem oferta presencial', 'SUM(CASE WHEN is_deserto THEN 1 ELSE 0 END)')] },
  b2_financiamento_ano: { desc: 'B2 · Peso de FIES e ProUni na rede privada. Grão: ano × modalidade.',
    cols: [I('nu_ano_censo', 'Ano do Censo'), T('modalidade'), I('nu_cursos'), I('qt_ingressante'), I('qt_ingressante_fies'), I('qt_ingressante_prouni'), I('qt_matricula'), I('qt_matricula_fies'), I('qt_matricula_prouni'), N('pct_ingressante_fies'), N('pct_ingressante_prouni'), N('pct_matricula_fies'), N('pct_matricula_prouni')],
    metrics: [m('FIES ingressantes', 'FIES (% dos ingressantes)', '100.0 * SUM(COALESCE(qt_ingressante_fies, 0)) / NULLIF(SUM(qt_ingressante), 0)', '.1f'), m('ProUni ingressantes', 'ProUni (% dos ingressantes)', '100.0 * SUM(COALESCE(qt_ingressante_prouni, 0)) / NULLIF(SUM(qt_ingressante), 0)', '.1f'),
      m('FIES matriculados', 'FIES (% dos matriculados)', '100.0 * SUM(COALESCE(qt_matricula_fies, 0)) / NULLIF(SUM(qt_matricula), 0)', '.1f'), m('ProUni matriculados', 'ProUni (% dos matriculados)', '100.0 * SUM(COALESCE(qt_matricula_prouni, 0)) / NULLIF(SUM(qt_matricula), 0)', '.1f'),
      m('Ingressantes', 'Ingressantes', 'SUM(qt_ingressante)'), m('Matrículas', 'Matrículas', 'SUM(qt_matricula)'), m('Cursos', 'Cursos', 'SUM(nu_cursos)')] },
  b2_financiamento_desistencia: { desc: 'B2 · Desistência no 4º ano por quartil de financiamento (cursos privados com 30+ ingressantes).',
    cols: [I('quartil_financiamento', 'Quartil de financiamento'), N('pct_financiado_min'), N('pct_financiado_max'), I('nu_cursos'), I('qt_ingressante'), I('qt_desistencia_marco'), N('taxa_desistencia_marco')],
    metrics: [m('Desistência', 'Saíram do curso em 4 anos (%)', WAVG('taxa_desistencia_marco'), '.1f'), m('Ingressantes', 'Ingressantes', 'SUM(qt_ingressante)'), m('Cursos', 'Cursos', 'SUM(nu_cursos)'), m('Financiado mínimo', '% financiado (mín.)', 'MIN(pct_financiado_min)', '.1f'), m('Financiado máximo', '% financiado (máx.)', 'MAX(pct_financiado_max)', '.1f')] },
  controle_atualizacao: { desc: 'Última carga de cada fonte.',
    cols: [T('fonte'), T('ultimo_status'), T('ultima_carga_sucesso_local', 'TIMESTAMP'), T('ultima_carga_sucesso_utc', 'TIMESTAMP'), I('linhas_ultima_execucao'), I('linhas_rejeitadas_ultima_execucao'), T('ultima_transformacao_local', 'TIMESTAMP'), T('fuso_horario')], metrics: [] },
};
Object.keys(DATASETS).forEach(k => { DATASETS[k].uuid = uuid('ds-gold-' + k); });
const ds = k => DATASETS[k];

// ───────────────────────── Construtores de gráfico ─────────────────────────
const charts = [];                       // {id, name, ds, params, desc}
let nextChartId = 1;
const eq = (col, v) => ({ expressionType: 'SIMPLE', subject: col, operator: '==', operatorId: 'EQUALS', comparator: v, clause: 'WHERE', isExtra: false });
const inn = (col, vs) => ({ expressionType: 'SIMPLE', subject: col, operator: 'IN', operatorId: 'IN', comparator: vs, clause: 'WHERE', isExtra: false });
const sqlw = s => ({ expressionType: 'SQL', sqlExpression: s, clause: 'WHERE', isExtra: false });
const having = s => ({ expressionType: 'SQL', sqlExpression: s, clause: 'HAVING', isExtra: false });
const K10 = (col) => having(`SUM(${col}) >= 10`);           // célula pequena: some do gráfico

function add(name, dsKey, params, desc) {
  const id = nextChartId++;
  charts.push({ id, name, ds: dsKey, desc, params: Object.assign({ viz_type: params.viz_type, adhoc_filters: [], extra_form_data: {}, dashboards: [] }, params) });
  return id;
}
// label_colors vale para o painel todo e casa pelo NOME da série. Por isso: toda métrica começa neutra
// (rankings e colunas simples nunca ficam vermelhos) e só o resultado da trajetória, as redes e o funil têm cor própria.
const LABELS = {};
Object.values(DATASETS).forEach(d => d.metrics.forEach(x => { LABELS[x.name] = C.neutro; LABELS[x.verbose] = C.neutro; }));
Object.assign(LABELS, { 'Concluíram': C.navy, 'Em curso': C.claro, 'Saíram do curso': C.saiu, 'Pública': C.navy, 'Privada': C.neutro, 'Presencial': C.navy, 'EAD': C.neutro,
  'Desistem': C.saiu, 'Concluem': C.navy, 'Concluem proficientes': C.neutro });

function kpi(name, dsKey, metric, fmt, sub, filters, desc) {
  return add(name, dsKey, { viz_type: 'big_number_total', metric, subheader: sub, y_axis_format: fmt, header_font_size: 0.6, subheader_font_size: 0.2, adhoc_filters: filters, color_picker: { r: 26, g: 43, b: 94, a: 1 }, force_timestamp_formatting: false }, desc);
}
function bar(name, dsKey, o, desc) {
  const horiz = o.horizontal;
  return add(name, dsKey, Object.assign({
    viz_type: 'echarts_timeseries_bar', x_axis: o.x, xAxisForceCategorical: true, metrics: o.metrics, groupby: o.groupby || [], adhoc_filters: o.filters || [],
    orientation: horiz ? 'horizontal' : 'vertical', stack: o.stack || null, show_value: o.showValue !== false, show_legend: !!(o.groupby && o.groupby.length) || o.metrics.length > 1,
    legendType: 'scroll', legendOrientation: 'top', row_limit: o.limit || 1000, order_desc: o.orderDesc !== false, color_scheme: 'univag', rich_tooltip: true, showTooltipTotal: !!o.stack,
    y_axis_format: o.fmt || '.1f', y_axis_title: o.yTitle || '', y_axis_title_margin: 40, x_axis_title: o.xTitle || '', x_axis_title_margin: 30, truncateYAxis: false, zoomable: false, minorTicks: false,
    x_axis_sort: o.sortBy === undefined ? o.x : o.sortBy, x_axis_sort_asc: o.sortBy === undefined ? true : o.sortAsc === true, sort_series_type: 'sum', sort_series_ascending: false, xAxisLabelRotation: 0, only_total: true, show_extra_controls: false, markerEnabled: false, forecastEnabled: false,
  }, o.extra || {}), desc);
}
function line(name, dsKey, o, desc) {
  return add(name, dsKey, {
    viz_type: 'echarts_timeseries_line', x_axis: o.x, xAxisForceCategorical: true, metrics: o.metrics, groupby: o.groupby || [], adhoc_filters: o.filters || [], row_limit: 1000, show_legend: true, legendType: 'scroll', legendOrientation: 'top',
    color_scheme: 'univag', rich_tooltip: true, y_axis_format: o.fmt || '.1f', y_axis_title: o.yTitle || '', y_axis_title_margin: 40, x_axis_title: o.xTitle || '', x_axis_title_margin: 30, markerEnabled: true, markerSize: 7, show_value: !!o.showValue, truncateYAxis: false, zoomable: false, forecastEnabled: false,
    opacity: 0.2, seriesType: 'line', order_desc: true,
  }, desc);
}
function table(name, dsKey, o, desc) {
  return add(name, dsKey, {
    viz_type: 'table', query_mode: o.raw ? 'raw' : 'aggregate', groupby: o.raw ? [] : o.groupby, metrics: o.raw ? [] : (o.metrics || []), all_columns: o.raw ? o.columns : [], percent_metrics: [], adhoc_filters: o.filters || [],
    order_by_cols: o.orderRaw ? [JSON.stringify(o.orderRaw)] : [], timeseries_limit_metric: o.sortMetric || null, order_desc: o.desc !== false, row_limit: o.limit || 1000, server_page_length: o.page || 10, include_search: true, table_timestamp_format: 'smart_date',
    show_cell_bars: false, color_pn: false, allow_render_html: false, column_config: o.colCfg || {}, conditional_formatting: [],
  }, desc);
}
function bubble(name, dsKey, o, desc) {
  return add(name, dsKey, {
    viz_type: 'bubble_v2', entity: o.entity, x: o.x, y: o.y, size: o.size, series: o.series || null, max_bubble_size: '10', row_limit: o.limit || 1000, adhoc_filters: o.filters || [], color_scheme: 'univag', show_legend: !!o.series, legendType: 'scroll', legendOrientation: 'top',
    x_axis_title: o.xTitle, y_axis_title: o.yTitle, x_axis_title_margin: 30, y_axis_title_margin: 40, xAxisFormat: o.xFmt || '.1f', y_axis_format: o.yFmt || '.1f', tooltipSizeFormat: ',d', opacity: 0.6, truncateXAxis: false, truncateYAxis: false, x_axis_bounds: [null, null], y_axis_bounds: [null, null], logAxis: false, xAxisLabelRotation: 0, orderby: [],
  }, desc);
}
function heat(name, dsKey, o, desc) {
  return add(name, dsKey, {
    viz_type: 'heatmap_v2', x_axis: o.x, groupby: o.y, metric: o.metric, adhoc_filters: o.filters || [], row_limit: o.limit || 10000, normalize_across: 'heatmap', legend_type: 'continuous', linear_color_scheme: 'univag_seq', show_legend: true, show_percentage: false, show_values: true,
    sort_x_axis: 'alpha_asc', sort_y_axis: 'value_desc', value_bounds: [null, null], y_axis_format: '.1f', xscale_interval: 1, yscale_interval: 1, left_margin: 'auto', bottom_margin: 'auto', canvas_image_rendering: 'pixelated',
  }, desc);
}
function pivot(name, dsKey, o, desc) {
  return add(name, dsKey, {
    viz_type: 'pivot_table_v2', groupbyRows: o.rows, groupbyColumns: o.cols, metrics: o.metrics, metricsLayout: o.metricsLayout || 'COLUMNS', adhoc_filters: o.filters || [], row_limit: 10000, aggregateFunction: 'Sum', transposePivot: false, combineMetric: false,
    rowTotals: false, colTotals: false, rowSubTotals: false, colSubTotals: false, valueFormat: o.fmt || '.1f', order_desc: true, series_limit: 0, date_format: 'smart_date', conditional_formatting: [], rowOrder: 'key_a_to_z', colOrder: 'key_a_to_z',
  }, desc);
}
// Cartão de KPI no estilo painel de operações: número grande, "chip" de contexto e subtítulo. Todo o texto sai pronto do SQL
// (formato pt-BR), o template só imprime. Handlebars não filtra por clique; os filtros da barra valem normalmente.
const intf = e => { const t = `CAST(${e} AS TEXT)`; return `CASE WHEN LENGTH(${t}) > 6 THEN SUBSTR(${t}, 1, LENGTH(${t}) - 6) || '.' || SUBSTR(${t}, LENGTH(${t}) - 5, 3) || '.' || SUBSTR(${t}, LENGTH(${t}) - 2) WHEN LENGTH(${t}) > 3 THEN SUBSTR(${t}, 1, LENGTH(${t}) - 3) || '.' || SUBSTR(${t}, LENGTH(${t}) - 2) ELSE ${t} END`; };
const txt = e => `REPLACE(CAST(ROUND(${e}, 1) AS TEXT), '.', ',')`;
function card(name, dsKey, o, desc) {
  const m1 = { expressionType: 'SQL', sqlExpression: `COALESCE((${o.value}) || '${o.unit || ''}', '—')`, label: 'v' };
  const mm = [m1];
  if (o.chip) mm.push({ expressionType: 'SQL', sqlExpression: o.chip, label: 'c' }, { expressionType: 'SQL', sqlExpression: o.chipKind || "'n'", label: 'k' });
  const tpl = `<div class="kpi${o.hero ? ' kpi-hero' : ''}"><div class="kpi-l">${o.label}</div><div class="kpi-v">{{#each data}}{{v}}{{/each}}</div><div class="kpi-s">${o.chip ? '{{#each data}}<span class="chip chip-{{k}}">{{c}}</span>{{/each}}' : ''}${o.sub}</div></div>`;
  return add(name, dsKey, { viz_type: 'handlebars', query_mode: 'aggregate', groupby: [], metrics: mm, all_columns: [], adhoc_filters: o.filters || [], row_limit: 1, order_desc: true, handlebarsTemplate: tpl, styleTemplate: '' }, desc);
}
const W = (id, w, h) => ({ c: id, w, h });                     // gráfico com largura (colunas de 12) e altura (unidades de 8 px)
const itemId = it => typeof it === 'object' && it.c !== undefined ? it.c : it;
function md(id, code, width = 12, height = 12) { return { md: true, id, code, width, height }; }


// ───────────────────────── Texto ─────────────────────────
const SRC_TRAJ = 'INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).';
const SRC_CENSO = 'INEP, Censo da Educação Superior (cursos), 2021–2024. Camada gold do warehouse (dbt).';
const HOW_PCT = 'Taxas já vêm calculadas na Gold (soma do numerador sobre soma do denominador) e, ao reagregar aqui, são ponderadas pelo número de ingressantes (nunca média simples). Grupos com menos de 10 alunos não são publicados.';
const WHERE_P1 = ' Por padrão, cursos presenciais (filtro Modalidade · trajetória).';

// ───────────────────────── Montagem dos gráficos por aba ─────────────────────────
const PRES = [];   // modalidade é filtro nativo (padrão Presencial), não mais fixa no gráfico
const ELEG = eq('is_elegivel_ranking', true);                 // ranking só com 30+ ingressantes (regra do dbt)
const HV30 = having('SUM(qt_ingressante) >= 30');
const tabs = [];

function kpiRowP1(tag) {
  const f = [...PRES, eq('nu_ano_referencia', 2024)];
  return [
    kpi(`${tag} · Concluíram (%)`, 'p1_trajetoria_coorte', 'Concluíram', '.1f', '% dos ingressantes da coorte · situação em 2024', f, 'Taxa de conclusão acumulada (TCA). ' + HOW_PCT + WHERE_P1 + ' Fonte: ' + SRC_TRAJ),
    kpi(`${tag} · Saíram do curso (%)`, 'p1_trajetoria_coorte', 'Saíram do curso', '.1f', '% dos ingressantes · inclui transferências · situação em 2024', f, 'Taxa de desistência acumulada (TDA). "Saíram do curso" não significa necessariamente abandono da graduação. ' + HOW_PCT + WHERE_P1 + ' Fonte: ' + SRC_TRAJ),
    kpi(`${tag} · Em curso (%)`, 'p1_trajetoria_coorte', 'Em curso', '.1f', '% dos ingressantes · cursando ou trancado · situação em 2024', f, 'Taxa de permanência (TAP). ' + HOW_PCT + WHERE_P1 + ' Fonte: ' + SRC_TRAJ),
    kpi(`${tag} · Total de ingressantes`, 'p1_trajetoria_coorte', 'Ingressantes', ',d', 'ingressantes da coorte (modalidade no filtro)', f, 'Soma de QT_INGRESSANTE da coorte nos cursos de MT (por padrão, presenciais).' + ' Fonte: ' + SRC_TRAJ),
  ];
}
function evolution(tag) {
  return bar(`${tag} · Situação da coorte ao fim de cada ano`, 'p1_trajetoria_coorte', { x: 'nu_ano_referencia', metrics: ['Concluíram', 'Saíram do curso', 'Em curso'], stack: 'Stack', filters: PRES, fmt: '.1f', yTitle: '% dos ingressantes', xTitle: 'Ano de referência', showValue: false },
    'Cada coluna soma 100%: concluíram + saíram do curso + em curso, acumulado até o ano. ' + HOW_PCT + WHERE_P1 + ' Fonte: ' + SRC_TRAJ);
}
function lossYear(tag) {
  return bar(`${tag} · Em que ano do curso a perda é maior?`, 'p1_trajetoria_coorte', { x: 'nu_ano_curso', metrics: ['Saídas no ano'], filters: PRES, fmt: '.1f', yTitle: '% da coorte que saiu no ano', xTitle: 'Ano do curso (1º = ano de ingresso)' },
    'Desistentes de cada ano sobre os ingressantes da coorte. A barra mais alta é o ano de maior perda. ' + WHERE_P1 + ' Fonte: ' + SRC_TRAJ);
}
function rankRotulo(tag, limit, menor) {
  return bar(`${tag} · Cursos com ${menor ? 'menor' : 'maior'} desistência no 4º ano`, 'p2_desistencia_curso', { x: 'no_cine_rotulo', metrics: ['Desistência'], limit, sortBy: 'Desistência', sortAsc: !!menor, orderDesc: !menor, filters: [...PRES, ELEG, HV30], fmt: '.1f', yTitle: '% que saiu do curso', extra: { xAxisLabelRotation: 45 } },
    'Cursos (rótulo CINE) ordenados pela desistência acumulada até o 4º ano do curso, na coorte escolhida. Só entram rótulos com 30 ou mais ingressantes. ' + HOW_PCT + WHERE_P1 + ' Fonte: ' + SRC_TRAJ);
}
function p3line(tag) {
  return line(`${tag} · Evasão anual por rede e modalidade`, 'p3_rede_modalidade_ano', { x: 'nu_ano_censo', metrics: ['Evasão anual'], groupby: ['rede', 'modalidade'], filters: [], yTitle: 'Evasão anual (%)', xTitle: 'Ano do Censo', showValue: false },
    'Evasão anual (proxy do Censo) = desvinculados ÷ (matriculados + desvinculados + transferidos), no ano. Mede a perda DAQUELE ano, não a da turma inteira. A Gold calcula com outro denominador (inclui trancadas e falecidos): veja "base Gold" na tabela de bases. Fonte: ' + SRC_CENSO);
}
function cpcBars(tag) {
  return bar(`${tag} · Desistência por faixa do CPC`, 'p4_qualidade_faixa', { x: 'faixa_cpc', metrics: ['Desistência'], filters: [], fmt: '.1f', yTitle: '% que saiu do curso em 4 anos', xTitle: 'CPC (faixa)' },
    'Desistência acumulada até o 4º ano por faixa do CPC, ponderada pelos ingressantes. "Sem CPC" (SC ou sem edição) não é nota zero. Associação observada, não causa. Fonte: INEP, CPC 2021–2023 + Trajetória. Camada gold.');
}

// ── Visão geral · gestão à vista: tudo numa tela de 1080 px, sem rolagem (cartões 17u + 2 linhas de 34u, em unidades de 8 px)
const OV = 'Visão geral · ';
const F24 = [eq('nu_ano_referencia', 2024)];
const wavg = r => WAVG(r);
const ev = "100.0 * SUM(CASE WHEN nu_ano_censo = @Y@ THEN qt_desvinculado END) / NULLIF(SUM(CASE WHEN nu_ano_censo = @Y@ THEN qt_matricula + qt_desvinculado + qt_transferido END), 0)";
const evA = ev.split('@Y@').join('2024'), evB = ev.split('@Y@').join('2023');
const kp = [
  card(OV + 'Concluíram', 'p1_trajetoria_coorte', { label: 'Concluíram o curso', value: txt(wavg('taxa_conclusao_acum')), unit: '%', sub: 'dos ingressantes · situação em 2024', hero: true, filters: F24 }, 'Taxa de conclusão acumulada (TCA) da coorte escolhida em 2024, ponderada pelos ingressantes. ' + HOW_PCT + ' Fonte: ' + SRC_TRAJ),
  card(OV + 'Saíram do curso', 'p1_trajetoria_coorte', { label: 'Saíram do curso', value: txt(wavg('taxa_desistencia_acum')), unit: '%', chip: "'≈ ' || " + txt(wavg('taxa_desistencia_acum') + ' / 10') + " || ' de cada 10'", sub: 'inclui transferências', filters: F24 }, 'Taxa de desistência acumulada (TDA) em 2024. "Saíram do curso" não significa necessariamente abandono da graduação. ' + HOW_PCT + ' Fonte: ' + SRC_TRAJ),
  card(OV + 'Em curso', 'p1_trajetoria_coorte', { label: 'Ainda em curso', value: txt(wavg('taxa_permanencia')), unit: '%', sub: 'cursando ou trancado', filters: F24 }, 'Taxa de permanência (TAP) em 2024. ' + HOW_PCT + ' Fonte: ' + SRC_TRAJ),
  card(OV + 'Ingressantes', 'p1_trajetoria_coorte', { label: 'Ingressantes da coorte', value: intf('SUM(qt_ingressante)'), sub: 'na coorte e modalidade do filtro', filters: F24 }, 'Soma de QT_INGRESSANTE da coorte. Fonte: ' + SRC_TRAJ),
  card(OV + 'Evasão anual', 'p3_rede_modalidade_ano', { label: 'Evasão anual · Censo 2024', value: txt(evA), unit: '%', chip: "CASE WHEN (" + evA + ") >= (" + evB + ") THEN '▲ ' ELSE '▼ ' END || " + txt('ABS((' + evA + ') - (' + evB + '))') + " || ' p.p. vs 2023'", chipKind: "CASE WHEN (" + evA + ") >= (" + evB + ") THEN 'bad' ELSE 'good' END", sub: 'desvinculados do ano', filters: [] }, 'Evasão anual (proxy do Censo) de 2024 e variação em pontos percentuais sobre 2023: desvinculados ÷ (matriculados + desvinculados + transferidos). Mede a perda DAQUELE ano. Fonte: ' + SRC_CENSO),
  card(OV + 'Municípios sem oferta', 'b1_desertos_municipio', { label: 'Municípios sem curso presencial', value: intf('SUM(CASE WHEN is_deserto THEN 1 ELSE 0 END)'), chip: "'de ' || " + intf('COUNT(*)') + " || ' no total'", sub: 'municípios de MT', filters: [] }, 'Municípios com zero vagas presenciais (is_deserto) entre os de MT. Detalhe na aba B1.'),
];
const g1 = bar(OV + 'A turma chega ao diploma?', 'p1_trajetoria_coorte', { x: 'nu_ano_referencia', metrics: ['Concluíram', 'Em curso', 'Saíram do curso'], stack: 'Stack', filters: [], fmt: '.0f', yTitle: '% dos ingressantes da coorte', xTitle: '', showValue: false, extra: { only_total: false, sort_series_type: 'name', sort_series_ascending: true, show_legend: true } },
  'Situação da coorte ao fim de cada ano (cada coluna soma 100%). ' + HOW_PCT + ' Fonte: ' + SRC_TRAJ);
const g2 = bar(OV + 'Em que ano do curso se perde mais?', 'p1_trajetoria_coorte', { x: 'nu_ano_curso', metrics: ['Saídas no ano'], filters: [], fmt: '.1f', yTitle: '% da coorte que saiu no ano', xTitle: 'Ano do curso' },
  'Desistentes de cada ano sobre os ingressantes da coorte. A barra mais alta é o ano de maior perda. Fonte: ' + SRC_TRAJ);
const g3 = bar(OV + 'A qualidade (CPC) retém?', 'p4_qualidade_curso', { x: 'faixa_cpc', metrics: ['Desistência'], filters: [], fmt: '.1f', yTitle: '% que saiu do curso em 4 anos', xTitle: 'CPC (faixa)' },
  'Desistência acumulada até o 4º ano por faixa do CPC (coortes somadas), ponderada pelos ingressantes. "Sem CPC" não é nota zero. Associação, não causa. Fonte: INEP, CPC 2021–2023 + Trajetória.');
const g4 = bar(OV + 'Quais cursos mais perdem alunos?', 'p2_desistencia_curso', { x: 'no_cine_rotulo', metrics: ['Desistência'], horizontal: true, limit: 8, sortBy: 'Desistência', sortAsc: true, filters: [ELEG, HV30], fmt: '.1f', yTitle: '% que saiu do curso até o 4º ano', extra: { y_axis_title_margin: 30 } },
  'Os 8 cursos (rótulo CINE) com maior desistência até o 4º ano do curso, na coorte escolhida. Só rótulos com 30 ou mais ingressantes. ' + HOW_PCT + ' Fonte: ' + SRC_TRAJ);
const g5 = line(OV + 'A evasão anual está subindo?', 'p3_rede_modalidade_ano', { x: 'nu_ano_censo', metrics: ['Evasão anual'], groupby: ['rede'], filters: [], yTitle: 'Evasão anual (%)', xTitle: '', showValue: true },
  'Evasão anual (proxy do Censo) por rede, na modalidade do filtro: desvinculados ÷ (matriculados + desvinculados + transferidos). Mede a perda daquele ano. Fonte: ' + SRC_CENSO);
const g6 = bar(OV + 'Licenciaturas: de cada 100 que entram', 'p5_funil_licenciaturas', { x: 'rede', metrics: ['Desistem', 'Concluem', 'Concluem proficientes'], horizontal: true, filters: [eq('rede', 'Total')], fmt: '.1f', yTitle: '', xTitle: '' },
  'Nas licenciaturas de MT: de cada 100 ingressantes, quantos desistem, concluem e concluem no padrão de proficiência do Enade 2025 (esta última etapa é estimativa: bases diferentes). Fonte: Trajetória + Enade Licenciaturas 2025.');
tabs.push({ id: 'overview', title: 'Visão geral', rows: [
  kp.map(id => W(id, 2, 17)),
  [W(g1, 5, 34), W(g2, 3, 34), W(g3, 4, 34)],
  [W(g4, 5, 34), W(g5, 4, 34), W(g6, 3, 34)],
] });

// ── P1
tabs.push({ id: 'p1', title: 'P1 · Trajetória', rows: [
  [md('md-p1', `### P1 · Quanto da turma fica pelo caminho?\nDos ingressantes da **coorte escolhida** nos cursos de MT (padrão: presenciais): que percentual **concluiu**, **saiu do curso** e **ainda estava no curso** em 2024? Em que ano do curso a perda é maior?\n*Use o filtro **Coorte** para comparar outras turmas.*`, 12, 15)],
  kpiRowP1('P1'),
  [evolution('P1'), lossYear('P1')],
  [table('P1 · Bases de cálculo por ano', 'p1_trajetoria_coorte', { groupby: ['nu_ano_referencia'], metrics: ['Concluíram', 'Saíram do curso', 'Em curso', 'Saídas no ano', 'Ingressantes'], filters: PRES, desc: false, page: 12 },
    'Mesmos números do gráfico, em tabela, com a base (ingressantes). ' + HOW_PCT + WHERE_P1 + ' Fonte: ' + SRC_TRAJ)],
] });

// ── P2
const p2Heat = heat('P2 · Área × coorte no mesmo ano do curso', 'p2_desistencia_area', { x: 'nu_ano_ingresso', y: 'no_cine_area_geral', metric: 'Desistência', filters: PRES, limit: 5000 },
  'Compara COORTES diferentes no MESMO ano do curso (filtro "Ano do curso"), nunca na mesma data. Cada célula é a desistência acumulada ponderada da área naquela coorte. Fonte: ' + SRC_TRAJ);
const p2Pivot = pivot('P2 · Curso (rótulo CINE) × coorte no 4º ano do curso', 'p2_desistencia_curso', { rows: ['no_cine_rotulo'], cols: ['nu_ano_ingresso'], metrics: ['Desistência'], fmt: '.1f', filters: [...PRES, ELEG, HV30] },
  'Desistência acumulada até o 4º ano do curso, por rótulo CINE e coorte. Só rótulos com 30+ ingressantes. Compare colunas (coortes) na mesma linha. Fonte: ' + SRC_TRAJ);
tabs.push({ id: 'p2', title: 'P2 · Cursos e áreas', rows: [
  [md('md-p2', `### P2 · Onde a rota mais se perde?\nCursos (rótulo CINE) e áreas com **maior** e **menor** desistência acumulada em MT, no **mesmo ano do curso**, comparando coortes.\n*Cursos: 4º ano do curso (padrão do dbt). Áreas: escolha o **Ano do curso** e a **Coorte** nos filtros.*
> **Interaja:** clique numa linha de **tabela** ou **tabela dinâmica** para filtrar os outros gráficos da aba (clique de novo para limpar; o filtro ativo aparece no topo) · botão direito num gráfico: *Detalhar por* e *Ver registros* · Área, Curso e Instituição se encadeiam.`, 12, 19)],
  [rankRotulo('P2', 10), rankRotulo('P2', 10, true)],
  [bar('P2 · Desistência por área geral (CINE)', 'p2_desistencia_area', { x: 'no_cine_area_geral', metrics: ['Desistência'], horizontal: true, sortBy: 'Desistência', sortAsc: true, filters: PRES, fmt: '.1f', yTitle: '% que saiu do curso', extra: { y_axis_title_margin: 30 } },
     'Áreas gerais CINE ordenadas pela desistência acumulada ponderada, no ano do curso e na coorte escolhidos. ' + WHERE_P1 + ' Fonte: ' + SRC_TRAJ),
   table('P2 · Bases de cálculo por curso (rótulo)', 'p2_desistencia_curso', { groupby: ['no_cine_rotulo'], metrics: ['Desistência', 'Ingressantes', 'Cursos'], filters: PRES, sortMetric: 'Desistência', desc: true, page: 10 },
    'Taxa (ponderada), base de ingressantes e número de cursos por rótulo, no 4º ano do curso. ' + WHERE_P1 + ' Fonte: ' + SRC_TRAJ)],
  [p2Heat],
  [p2Pivot],
] });

// ── P3
tabs.push({ id: 'p3', title: 'P3 · Rede e modalidade', rows: [
  [md('md-p3', `### P3 · Pública × privada, presencial × EAD\nComo a **evasão anual** e a **distribuição das matrículas** variam entre rede pública e privada e entre presencial e EAD, de **2021 a 2024**? Há algum **ano atípico**?\n> **Evasão anual (Censo) ≠ desistência acumulada (Trajetória).** Aqui a medida é a perda de um único ano. A Gold separa só Pública/Privada: a divisão da privada em com e sem fins lucrativos não está nela.`, 12, 19)],
  [p3line('P3'),
   bar('P3 · Distribuição das matrículas', 'p3_rede_modalidade_ano', { x: 'nu_ano_censo', metrics: ['Matrículas'], groupby: ['rede', 'modalidade'], stack: 'Expand', filters: [], fmt: '.0%', yTitle: '% das matrículas', xTitle: 'Ano do Censo', showValue: false },
     'Participação de cada rede × modalidade no total de matrículas do ano (colunas somam 100%). Fonte: ' + SRC_CENSO)],
  [bar('P3 · Variação da evasão (p.p. sobre o ano anterior)', 'p3_rede_modalidade_ano', { x: 'nu_ano_censo', metrics: ['Variação da evasão pp'], groupby: ['rede', 'modalidade'], filters: [], fmt: '.1f', yTitle: 'p.p.', xTitle: 'Ano do Censo' },
     'Diferença em pontos percentuais da evasão para o ano anterior (calculada na Gold). Destaca ano atípico: um valor que dispara e volta ao normal pede investigação antes de virar conclusão. Fonte: ' + SRC_CENSO),
   bar('P3 · Variação das matrículas (% sobre o ano anterior)', 'p3_rede_modalidade_ano', { x: 'nu_ano_censo', metrics: ['Variação das matrículas pct'], groupby: ['rede', 'modalidade'], filters: [], fmt: '.1f', yTitle: '%', xTitle: 'Ano do Censo' },
     'Variação percentual das matrículas sobre o ano anterior (Gold). Saltos (ex.: 2023) pedem explicação antes da conclusão. Fonte: ' + SRC_CENSO)],
  [table('P3 · Bases da evasão anual', 'p3_rede_modalidade_ano', { groupby: ['nu_ano_censo', 'rede', 'modalidade'], metrics: ['Evasão anual', 'Evasão anual base Gold', 'Desvinculados', 'Base da evasão', 'Matrículas'], filters: [], desc: false, page: 12 },
     'Numerador (desvinculados) e denominador (matriculados + desvinculados + transferidos) da evasão anual, e a taxa com a base da Gold (que inclui trancadas e falecidos). Fonte: ' + SRC_CENSO)],
] });

// ── P4
tabs.push({ id: 'p4', title: 'P4 · CPC e desistência', rows: [
  [md('md-p4', `### P4 · Qualidade retém?\nCursos com **CPC mais alto** (ciclo 2021–2023) têm **desistência menor**? Mostre a relação e discuta o que mais pode explicá-la.\n> **Associação observada, não causa.** Cursos *sem CPC* ficam de fora da comparação: ausência de nota **não** é zero. Rede, modalidade e os componentes do CPC também explicam parte da relação (gráficos de controle e de fatores).`, 12, 19)],
  [cpcBars('P4'),
   bubble('P4 · CPC contínuo × desistência (um ponto por curso)', 'p4_qualidade_curso', { entity: 'co_curso', x: { expressionType: 'SQL', sqlExpression: 'MAX(cpc_continuo)', label: 'CPC (contínuo)' }, y: { expressionType: 'SQL', sqlExpression: 'MAX(taxa_desistencia_marco)', label: 'Saíram do curso (%)' }, size: { expressionType: 'SQL', sqlExpression: 'SUM(qt_ingressante)', label: 'Ingressantes' }, series: 'rede',
      filters: [sqlw('cpc_continuo IS NOT NULL'), ELEG], xTitle: 'CPC (contínuo, 0–5)', yTitle: '% que saiu do curso em 4 anos', limit: 2000 },
      'Cada bolha é um curso (tamanho = ingressantes), cor = rede. Só cursos com CPC e 30+ ingressantes. Associação, não causa. Fonte: INEP, CPC 2021–2023 + Trajetória.')],
  [bar('P4 · Controle: faixa do CPC × rede', 'p4_qualidade_faixa', { x: 'faixa_cpc', metrics: ['Desistência'], groupby: ['rede'], filters: [], fmt: '.1f', yTitle: '% que saiu do curso', xTitle: 'CPC (faixa)' },
      'Mesma comparação separada por rede: se a relação some dentro de cada rede, a rede explica parte do efeito aparente.'),
   bar('P4 · Controle: faixa do CPC × modalidade', 'p4_qualidade_curso', { x: 'faixa_cpc', metrics: ['Desistência'], groupby: ['modalidade'], filters: [], fmt: '.1f', yTitle: '% que saiu do curso', xTitle: 'CPC (faixa)' },
      'Mesma comparação separada por modalidade (presencial × EAD).')],
  [bar('P4 · O que mais explica a desistência (correlação)', 'p4_fatores', { x: 'fator', metrics: ['Correlação com a desistência'], horizontal: true, sortBy: 'Correlação com a desistência', sortAsc: true, filters: [], fmt: '.2f', yTitle: 'correlação de Pearson com a desistência no 4º ano', extra: { y_axis_title_margin: 30 } },
      'Correlação de Pearson (um curso, um ponto, não ponderada) de cada componente do CPC com a taxa de desistência no 4º ano. Valores positivos: mais do fator, mais desistência. Correlação não é causa.'),
   table('P4 · Cobertura e bases por faixa', 'p4_qualidade_curso', { groupby: ['faixa_cpc'], metrics: ['Cursos', 'Ingressantes', 'Desistência'], filters: [], desc: false, page: 8 },
      'Quantos cursos e ingressantes há em cada faixa, incluindo "Sem CPC" (cobertura). Taxa ponderada pelos ingressantes.')],
] });

// ── P5
const FUN = [eq('rede', 'Total')];
tabs.push({ id: 'p5', title: 'P5 · Licenciaturas', rows: [
  [md('md-p5', `### P5 · O funil das licenciaturas\nNas licenciaturas de MT: quanto da turma **desiste** e quanto dos **concluintes atinge o padrão de proficiência** no Enade 2025? Quais áreas **formam pouco e com baixa proficiência**?\n> **Bases diferentes:** a desistência é da Trajetória; a proficiência é de quem **concluiu e fez o Enade 2025**. Não são os mesmos estudantes: a última etapa do funil é estimativa.`, 12, 19)],
  [kpi('P5 · Ingressantes em licenciaturas', 'p5_funil_licenciaturas', 'Ingressantes', ',d', 'ingressantes (coortes 2015–2020)', FUN, 'Soma de QT_INGRESSANTE das licenciaturas de MT. Fonte: ' + SRC_TRAJ),
   kpi('P5 · Desistem (de cada 100)', 'p5_funil_licenciaturas', 'Desistem', '.1f', 'de cada 100 que entram', FUN, 'Desistentes no último ano observado sobre ingressantes. Fonte: ' + SRC_TRAJ),
   kpi('P5 · Concluem (de cada 100)', 'p5_funil_licenciaturas', 'Concluem', '.1f', 'de cada 100 que entram', FUN, 'Concluintes no último ano observado sobre ingressantes. Fonte: ' + SRC_TRAJ),
   kpi('P5 · Concluem proficientes (de cada 100)', 'p5_funil_licenciaturas', 'Concluem proficientes', '.1f', 'estimativa · Enade 2025', FUN, 'Concluem × % de concluintes no padrão de proficiência (Enade 2025). Estimativa: os concluintes do Enade não são a mesma turma. Fonte: INEP, Conceito Enade 2025 · Licenciaturas.')],
  [bar('P5 · Funil por rede (de cada 100 que entram)', 'p5_funil_licenciaturas', { x: 'rede', metrics: ['Desistem', 'Concluem', 'Concluem proficientes'], filters: [], fmt: '.1f', yTitle: 'de cada 100 ingressantes', xTitle: 'Rede' },
      'Para cada rede e para o total: quantos de cada 100 ingressantes desistem, concluem e concluem proficientes (estimativa). Fonte: Trajetória + Enade Licenciaturas 2025. Camada gold.'),
   bar('P5 · Desistência por licenciatura', 'p5_licenciaturas_curso', { x: 'no_curso', metrics: ['Desistência'], horizontal: true, limit: 15, sortBy: 'Desistência', sortAsc: true, filters: [], yTitle: '% que saiu do curso', extra: { y_axis_title_margin: 30 } },
      'As 15 licenciaturas com maior desistência até o último ano observado, ponderada pelos ingressantes (somando instituições). Fonte: ' + SRC_TRAJ)],
  [bar('P5 · Proficiência por área (Enade 2025)', 'p5_licenciaturas_curso', { x: 'area_enade', metrics: ['No padrão de proficiência'], horizontal: true, limit: 15, orderDesc: false, sortBy: 'No padrão de proficiência', sortAsc: false, filters: [sqlw('tem_enade')], yTitle: '% no padrão de proficiência ou acima', extra: { y_axis_title_margin: 30 } },
      'As 15 áreas com menor % de concluintes participantes no padrão de proficiência ou acima (Enade, ponderado por participantes). Células com menos de 10 participantes não são publicadas. Fonte: INEP, Conceito Enade 2025 · Licenciaturas.'),
   bubble('P5 · Quem forma pouco e com baixa proficiência', 'p5_licenciaturas_curso', { entity: 'co_curso', series: 'no_curso', x: { expressionType: 'SQL', sqlExpression: 'MAX(pct_proficiente)', label: 'No padrão ou acima (%)' }, y: { expressionType: 'SQL', sqlExpression: 'MAX(taxa_desistencia_final)', label: 'Saíram do curso (%)' }, size: { expressionType: 'SQL', sqlExpression: 'SUM(qt_participante_enade)', label: 'Concluintes participantes' },
      filters: [sqlw('tem_enade')], xTitle: '% dos concluintes no padrão de proficiência (quanto menor, pior)', yTitle: '% da coorte que saiu do curso (quanto maior, pior)' },
      'Cada bolha é um curso de licenciatura, colorido pela licenciatura. Canto superior-esquerdo = muita desistência e baixa proficiência. Tamanho = concluintes participantes (formam pouco = bolha pequena). Bases distintas.')],
  [table('P5 · Bases de cálculo por licenciatura', 'p5_licenciaturas_curso', { groupby: ['no_curso'], metrics: ['Cursos', 'Ingressantes', 'Desistência', 'Participantes do Enade', 'No padrão de proficiência'], filters: [], sortMetric: 'Desistência', page: 10 },
      'Bases de cada medida. Desistência: Trajetória. Proficiência: Enade 2025 (vazia onde não há participantes suficientes).')],
] });

// ── B1
tabs.push({ id: 'b1', title: 'B1 · Desertos de ensino superior', rows: [
  [md('md-b1', `### B1 · Desertos de ensino superior\nQuantas **vagas presenciais** de graduação há para cada **100 jovens de 18–24 anos** em cada município de MT? Onde estão os municípios **sem oferta**?\n> Vagas presenciais do Censo da Educação Superior ÷ população de 18–24 anos (IBGE, Censo 2022). **Zero é zero registrado** (município sem curso presencial), não ausência de dado. Município = local de oferta; EAD fica de fora.`, 12, 19)],
  [kpi('B1 · Vagas por 100 jovens (MT)', 'b1_desertos_municipio', 'Vagas por 100 jovens', '.1f', 'vagas presenciais ÷ jovens de 18 a 24 anos', [], 'Soma das vagas ÷ soma da população dos municípios do recorte. Fonte: INEP, Censo da Educação Superior; IBGE/SIDRA tabela 9514 (Censo 2022).'),
   kpi('B1 · Municípios sem oferta presencial', 'b1_desertos_municipio', 'Municípios sem oferta', ',d', 'municípios com zero vagas presenciais', [], 'Contagem de municípios com zero vagas presenciais (is_deserto).'),
   kpi('B1 · Municípios', 'b1_desertos_municipio', 'Municípios', ',d', 'municípios no recorte', [], 'Todos os municípios de MT vêm do IBGE; quem não tem curso entra com zero vagas.'),
   kpi('B1 · Vagas presenciais', 'b1_desertos_municipio', 'Vagas', ',d', 'vagas presenciais de graduação', [], 'Soma de vagas presenciais dos cursos de graduação.')],
  [bar('B1 · Municípios com maior oferta (vagas por 100 jovens)', 'b1_desertos_municipio', { x: 'no_municipio', metrics: ['Vagas por 100 jovens'], limit: 15, sortBy: 'Vagas por 100 jovens', sortAsc: false, filters: [], yTitle: 'vagas presenciais por 100 jovens', extra: { xAxisLabelRotation: 45 } }, 'Os 15 municípios com mais vagas presenciais por 100 jovens de 18 a 24 anos.'),
   bar('B1 · Quantos municípios em cada faixa de oferta', 'b1_desertos_municipio', { x: 'faixa_oferta', metrics: ['Municípios'], fmt: ',d', filters: [], yTitle: 'municípios', xTitle: 'Faixa (vagas por 100 jovens)' }, 'Distribuição dos municípios por faixa de vagas por 100 jovens. "Sem oferta" = zero vagas presenciais.')],
  [table('B1 · Maiores desertos (sem oferta, por população jovem)', 'b1_desertos_municipio', { raw: true, columns: ['no_municipio', 'nu_populacao_18_24', 'nu_vagas_presenciais', 'vagas_por_100_jovens'], filters: [sqlw('is_deserto')], orderRaw: ['nu_populacao_18_24', false], page: 12 },
      'Municípios sem nenhuma vaga presencial, ordenados pela população de 18 a 24 anos (onde há mais jovens sem oferta local).')],
] });

// ── B2
tabs.push({ id: 'b2', title: 'B2 · Financiamento', rows: [
  [md('md-b2', `### B2 · Financiamento e permanência\nQual o peso do **FIES** e do **ProUni** entre os ingressantes da rede **privada** de MT (2021–2024)? Cursos com **mais financiados evadem menos**?\n> Comparamos **cursos** agrupados por quartil de participação do financiamento (dados agregados por curso, não por aluno). **Associação, não causa:** cursos com mais bolsistas diferem em área, modalidade e perfil.`, 12, 19)],
  [bar('B2 · Peso do FIES e do ProUni entre os ingressantes', 'b2_financiamento_ano', { x: 'nu_ano_censo', metrics: ['FIES ingressantes', 'ProUni ingressantes'], groupby: ['modalidade'], filters: [], yTitle: '% dos ingressantes da rede privada', xTitle: 'Ano do Censo' }, 'Participação de FIES e de ProUni (integral + parcial), separadamente, entre os ingressantes da rede privada. Os programas não são somados entre si. Fonte: ' + SRC_CENSO),
   bar('B2 · Peso do FIES e do ProUni entre os matriculados', 'b2_financiamento_ano', { x: 'nu_ano_censo', metrics: ['FIES matriculados', 'ProUni matriculados'], groupby: ['modalidade'], filters: [], yTitle: '% dos matriculados da rede privada', xTitle: 'Ano do Censo' }, 'Mesma leitura, agora sobre os matriculados. Fonte: ' + SRC_CENSO)],
  [bar('B2 · Desistência no 4º ano por quartil de financiamento', 'b2_financiamento_desistencia', { x: 'quartil_financiamento', metrics: ['Desistência'], filters: [], yTitle: '% que saiu do curso em 4 anos', xTitle: 'Quartil de % financiado (1 = menos financiados, 4 = mais)' }, 'Cursos privados com 30+ ingressantes divididos em quartis pela participação média de financiamento; desistência ponderada em cada quartil. Associação, não causa. Fonte: Trajetória + Censo. Camada gold.'),
   table('B2 · Bases de cálculo por quartil', 'b2_financiamento_desistencia', { groupby: ['quartil_financiamento'], metrics: ['Financiado mínimo', 'Financiado máximo', 'Cursos', 'Ingressantes', 'Desistência'], filters: [], desc: false, page: 6 }, 'Faixa de % financiado de cada quartil, número de cursos, ingressantes e taxa.')],
  [table('B2 · Bases de cálculo por ano', 'b2_financiamento_ano', { groupby: ['nu_ano_censo', 'modalidade'], metrics: ['Cursos', 'Ingressantes', 'FIES ingressantes', 'ProUni ingressantes', 'FIES matriculados', 'ProUni matriculados'], filters: [], desc: false, page: 8 }, 'Cursos, ingressantes e taxas por ano e modalidade na rede privada. Fonte: ' + SRC_CENSO)],
] });

// ── Fontes e método
const METH = [
  ['Concluíram · Saíram do curso · Em curso', 'Situação dos ingressantes da coorte em 2024, no curso de ingresso. **Concluíram** = TCA; **Saíram do curso** = TDA (desvinculados e transferidos, não é necessariamente abandono da graduação); **Em curso** = TAP (cursando ou trancado). As três somam ≈100%.', 'Taxa = soma do numerador ÷ soma do denominador, calculada na Gold; ao reagregar no painel, ponderada pelos ingressantes.'],
  ['Desistência por curso e área', 'Desistência acumulada (TDA) no mesmo **ano do curso**, nunca na mesma data. Coortes diferentes só se comparam no mesmo horizonte. Cursos: 4º ano. Áreas: ano do curso à escolha.', 'Ranking de cursos só com 30 ou mais ingressantes (regra do dbt).'],
  ['Evasão anual por rede e modalidade', 'Evasão anual (proxy do Censo) = **desvinculados ÷ (matriculados + desvinculados + transferidos)**, no ano. Mede o fluxo de um ano; **não se compara** à desistência acumulada de coorte.', 'A Gold publica `taxa_evasao_anual` com denominador mais amplo (inclui trancadas e falecidos). O painel mostra as duas.'],
  ['CPC × desistência', 'Desistência no 4º ano de cada curso (coortes somadas) ligada ao CPC mais recente do curso (2021–2023) pelo código do curso. Cursos sem CPC ficam como "Sem CPC" (não é zero).', 'Taxa ponderada pelos ingressantes. Correlação por componente do CPC em "O que mais explica". Associação, não causa.'],
  ['Licenciaturas · Enade 2025', 'Funil de cada 100 ingressantes: desistem, concluem e concluem proficientes. A proficiência vem dos concluintes do Enade 2025, **que não são a mesma turma**: a última etapa é estimativa.', 'Ligação apenas pelo curso, sem vínculo individual.'],
  ['Desertos · FIES e ProUni', 'Vagas presenciais ÷ jovens de 18–24 anos (Censo da Educação Superior ÷ IBGE 2022); FIES e ProUni como % dos ingressantes/matriculados da rede privada; desistência por quartil de financiamento.', 'Fontes de anos diferentes; vagas não equivalem a matrículas.'],
];
tabs.push({ id: 'fontes', title: 'Fontes e metodologia', rows: [
  [md('md-fontes', `### Fontes de dados\n| Fonte | Edição | Usada em |\n|---|---|---|\n| INEP · Indicadores de Trajetória da Educação Superior | Coortes 2015–2020, até 2024 | P1, P2, P4, P5 |\n| INEP · Censo da Educação Superior (cursos) | 2021–2024 | P3, B1, B2 |\n| INEP · Conceito Preliminar de Curso (CPC) | 2021, 2022, 2023 | P4 |\n| INEP · Conceito Enade 2025 · Licenciaturas | 2025 | P5 |\n| IBGE/SIDRA · tabela 9514 (Censo Demográfico) | 2022 | B1 |\n\nSomente dados públicos. **Associação, não causa.** Grupos com menos de 10 alunos não são exibidos. Este painel lê o schema **gold** do warehouse (publicado pelo dbt após os portões de qualidade).`, 12, 52)],
  [
   md('md-glos', `### Definições\n- **Coorte**: turma que ingressou num curso num mesmo ano.\n- **TDA / TCA / TAP**: desistência, conclusão e permanência acumuladas (% dos ingressantes).\n- **Ano do curso**: tempo de acompanhamento da coorte (2015 = 1º ano, 2019 = 5º).\n- **Evasão anual**: perda de um único ano, medida no Censo.\n- **% e p.p.**: percentual é proporção; ponto percentual é diferença entre percentuais.\n- **Sem dados ≠ zero.** Vazio, "--" e "SC" são ausência de dado.\n- **EAD**: o município é o do polo, não o do aluno.\n- **Taxa média é ponderada** pelo nº de ingressantes (ou de matrículas).`, 12, 30)],
  [md('md-metodo', `### Como cada indicador é calculado\nUm bloco por painel: o que o número significa, de onde vem e como é agregado.`, 12, 14)],
  // dois cartões por linha; altura folgada para o texto não rolar em telas menores
  ...[0, 2, 4].map(i => METH.slice(i, i + 2).map(([t, d, f], j) => md('md-m' + (i + j), `#### ${t}\n${d}\n\n*${f}*`, 6, 26))),
  [table('Atualização · última carga de cada fonte', 'controle_atualizacao', { raw: true, columns: ['fonte', 'ultimo_status', 'ultima_carga_sucesso_local', 'linhas_ultima_execucao', 'linhas_rejeitadas_ultima_execucao', 'ultima_transformacao_local', 'fuso_horario'], filters: [], page: 10 }, 'Quando cada fonte foi carregada e quantas linhas foram lidas/rejeitadas (tabela controle_atualizacao da Gold).')],
] });

// ───────────────────────── Filtros nativos ─────────────────────────
// Casam por NOME de coluna entre datasets; cada um vale só nas abas em 'tabs' (nas outras fica em "fora de escopo").
//   type 'range' = controle deslizante; cascade = filtros pai (as opções do filho encolhem conforme o pai);
//   exclude = função com os gráficos que o filtro NÃO deve tocar.
const tabId = id => 'TAB-' + id;
const chartsOf = (...dsKeys) => charts.filter(c => dsKeys.includes(c.ds)).map(c => c.id);
const FILTERS = [
  // trajetória (Visão geral, P1, P2)
  { key: 'coorte', name: 'Coorte (ano de ingresso)', ds: 'p1_trajetoria_coorte', col: 'nu_ano_ingresso', tabs: ['overview', 'p1', 'p2'], multi: false, required: true, first: true, exclude: () => [p2Heat, p2Pivot],
    desc: 'Turma que entrou no mesmo ano. Compare coortes trocando o valor; as matrizes de coorte do P2 já mostram todas.' },
  { key: 'modalidade_traj', name: 'Modalidade (trajetória)', ds: 'p1_trajetoria_coorte', col: 'modalidade', tabs: ['overview', 'p1', 'p2'], def: ['Presencial'],
    desc: 'Presencial ou EAD. Padrão: Presencial. Limpe o filtro para somar as duas (taxas sempre ponderadas pelos ingressantes).' },
  { key: 'ano_curso', name: 'Ano do curso (áreas)', ds: 'p2_desistencia_area', col: 'nu_ano_curso', tabs: ['p2'], def: [4], multi: false, required: true,
    desc: 'Horizonte de acompanhamento da coorte (1º ao 5º ano do curso). Vale só para o gráfico e a matriz de áreas.' },
  // perfil do curso (P2, P4, P5)
  { key: 'rede', name: 'Rede', ds: 'p2_desistencia_curso', col: 'rede', tabs: ['p2', 'p3', 'p4', 'p5'], exclude: () => chartsOf('p5_funil_licenciaturas'),
    desc: 'Pública ou privada. No P5, o funil por rede já compara as duas e não é filtrado.' },
  { key: 'modalidade', name: 'Modalidade', ds: 'p3_rede_modalidade_ano', col: 'modalidade', tabs: ['p3', 'p4', 'p5', 'b2'],
    desc: 'Presencial ou EAD. Vazio = as duas.' },
  { key: 'grau', name: 'Grau acadêmico', ds: 'p2_desistencia_curso', col: 'grau_academico', tabs: ['p2', 'p4'],
    desc: 'Bacharelado, licenciatura ou tecnológico.' },
  { key: 'area_cine', name: 'Área (CINE)', ds: 'p2_desistencia_curso', col: 'no_cine_area_geral', tabs: ['p2', 'p4', 'p5'],
    desc: 'Área geral da classificação CINE. Filtra a lista de cursos e de instituições.' },
  { key: 'rotulo_cine', name: 'Curso (rótulo CINE)', ds: 'p2_desistencia_curso', col: 'no_cine_rotulo', tabs: ['p2'], cascade: ['area_cine', 'grau'], search: true,
    desc: 'Rótulo do curso na CINE (ex.: Direito, Enfermagem). Mostra só os rótulos da área escolhida.' },
  { key: 'no_ies', name: 'Instituição', ds: 'p2_desistencia_curso', col: 'no_ies', tabs: ['p2', 'p4', 'p5'], cascade: ['rede', 'area_cine'], search: true,
    desc: 'Instituição de ensino. Mostra só as da rede e da área escolhidas.' },
  // qualidade (P4)
  { key: 'faixa_cpc', name: 'Faixa do CPC', ds: 'p4_qualidade_curso', col: 'faixa_cpc', tabs: ['p4'],
    desc: 'CPC 1 a 5 ou "Sem CPC" (ausência de nota não é nota zero).' },
  { key: 'cpc', name: 'CPC contínuo (0–5)', ds: 'p4_qualidade_curso', col: 'cpc_continuo', tabs: ['p4'], type: 'range',
    desc: 'Arraste para recortar cursos por nota. Cursos sem CPC saem enquanto o recorte estiver ativo.' },
  // licenciaturas (P5)
  { key: 'licenciatura', name: 'Licenciatura', ds: 'p5_licenciaturas_curso', col: 'no_curso', tabs: ['p5'], cascade: ['rede'], exclude: () => chartsOf('p5_funil_licenciaturas'), search: true,
    desc: 'Cada licenciatura de MT (somando instituições).' },
  { key: 'area_enade', name: 'Área de avaliação (Enade)', ds: 'p5_licenciaturas_curso', col: 'area_enade', tabs: ['p5'], exclude: () => chartsOf('p5_funil_licenciaturas'),
    desc: 'Área do Enade 2025. Só existe para cursos com concluintes participantes.' },
  // Censo (P3, B2)
  { key: 'ano_censo', name: 'Ano do Censo', ds: 'p3_rede_modalidade_ano', col: 'nu_ano_censo', tabs: ['p3', 'b2'],
    desc: 'Ano do Censo da Educação Superior (2021–2024). Vazio = todos.' },
  { key: 'quartil', name: 'Quartil de financiamento', ds: 'b2_financiamento_desistencia', col: 'quartil_financiamento', tabs: ['b2'],
    desc: '1 = cursos privados com menos financiados (FIES/ProUni); 4 = com mais.' },
  // desertos (B1)
  { key: 'municipio', name: 'Município', ds: 'b1_desertos_municipio', col: 'no_municipio', tabs: ['b1'], search: true,
    desc: 'Um ou vários municípios de MT.' },
  { key: 'faixa_oferta', name: 'Faixa de oferta', ds: 'b1_desertos_municipio', col: 'faixa_oferta', tabs: ['b1'],
    desc: 'Vagas presenciais por 100 jovens de 18 a 24 anos. "Sem oferta" = zero vagas.' },
  { key: 'vagas100', name: 'Vagas por 100 jovens', ds: 'b1_desertos_municipio', col: 'vagas_por_100_jovens', tabs: ['b1'], type: 'range',
    desc: 'Arraste para ver só municípios com oferta dentro da faixa.' },
  { key: 'jovens', name: 'Jovens de 18 a 24 anos', ds: 'b1_desertos_municipio', col: 'nu_populacao_18_24', tabs: ['b1'], type: 'range',
    desc: 'Tamanho da população jovem do município (IBGE 2022). Use para achar desertos grandes.' },
];
const fid = key => 'NATIVE_FILTER-' + uuid('nf' + key).slice(0, 12);
// Falha cedo (no build) se um filtro apontar para coluna, aba ou pai que não existe.
FILTERS.forEach(f => {
  const cols = ds(f.ds).cols.map(c => c.n);
  if (!cols.includes(f.col)) throw new Error(`filtro ${f.key}: coluna ${f.col} não existe em ${f.ds}`);
  f.tabs.forEach(t => { if (!tabs.some(x => x.id === t)) throw new Error(`filtro ${f.key}: aba ${t} não existe`); });
  (f.cascade || []).forEach(p => { if (!FILTERS.some(x => x.key === p)) throw new Error(`filtro ${f.key}: pai ${p} não existe`); });
});
function nativeFilters() {
  return FILTERS.map(f => {
    const val = f.def, range = f.type === 'range';
    return {
      id: fid(f.key), name: f.name, filterType: range ? 'filter_range' : 'filter_select', type: 'NATIVE_FILTER', description: f.desc || '',
      controlValues: range ? { enableEmptyFilter: false, inverseSelection: false }
        : { enableEmptyFilter: !!f.required, defaultToFirstItem: !!f.first, multiSelect: f.multi !== false, searchAllOptions: !!f.search, inverseSelection: false, sortAscending: true },
      targets: [{ datasetUuid: ds(f.ds).uuid, column: { name: f.col } }],
      defaultDataMask: val ? { extraFormData: { filters: [{ col: f.col, op: 'IN', val }] }, filterState: { value: val }, ownState: {} } : { extraFormData: {}, filterState: {}, ownState: {} },
      cascadeParentIds: (f.cascade || []).map(fid), scope: { rootPath: f.tabs.map(tabId), excluded: f.exclude ? f.exclude() : [] },
    };
  });
}

// Filtro cruzado: clicar numa barra/ponto/célula filtra os outros gráficos DA MESMA ABA (quem tem a coluna).
function crossFilterConfig() {
  const cfg = {};
  tabs.forEach(t => {
    const ids = t.rows.flat().map(itemId).filter(x => typeof x === 'number');
    ids.forEach(id => { cfg[id] = { id, crossFilters: { scope: { rootPath: [tabId(t.id)], excluded: [id] }, chartsInScope: ids.filter(o => o !== id) } }; });
  });
  return cfg;
}

// ───────────────────────── Layout (position JSON) ─────────────────────────
function widthsFor(n, mdW) { return n === 1 ? 12 : n === 2 ? 6 : n === 3 ? 4 : n === 4 ? 3 : Math.floor(12 / n); }
function buildPosition() {
  const pos = { DASHBOARD_VERSION_KEY: 'v2', ROOT_ID: { type: 'ROOT', id: 'ROOT_ID', children: ['GRID_ID'] }, GRID_ID: { type: 'GRID', id: 'GRID_ID', children: [], parents: ['ROOT_ID'] }, HEADER_ID: { id: 'HEADER_ID', type: 'HEADER', meta: { text: 'Rota do Diploma · Mato Grosso' } } };
  const gridParents = ['ROOT_ID', 'GRID_ID'];
  if (DEMO) {
    pos['ROW-banner'] = { type: 'ROW', id: 'ROW-banner', children: ['MARKDOWN-banner'], parents: gridParents, meta: { background: 'BACKGROUND_TRANSPARENT' } };
    pos['MARKDOWN-banner'] = { type: 'MARKDOWN', id: 'MARKDOWN-banner', children: [], parents: [...gridParents, 'ROW-banner'], meta: { width: 12, height: 8, code: '**⚠ DADOS DEMONSTRATIVOS** · números sintéticos para validar o painel, sem validade oficial. Para os dados reais do INEP/IBGE, rode o script 10_marts_from_staging.sql.' } };
    pos.GRID_ID.children.push('ROW-banner');
  }
  pos['TABS-main'] = { type: 'TABS', id: 'TABS-main', children: tabs.map(t => tabId(t.id)), parents: gridParents };
  pos.GRID_ID.children.push('TABS-main');
  let r = 0;
  tabs.forEach(t => {
    const tp = [...gridParents, 'TABS-main', tabId(t.id)];
    pos[tabId(t.id)] = { type: 'TAB', id: tabId(t.id), children: [], parents: [...gridParents, 'TABS-main'], meta: { text: t.title } };
    t.rows.forEach(row => {
      const rid = 'ROW-' + (++r);
      pos[rid] = { type: 'ROW', id: rid, children: [], parents: tp, meta: { background: 'BACKGROUND_TRANSPARENT' } };
      pos[tabId(t.id)].children.push(rid);
      const items = (Array.isArray(row) ? row : [row]);
      const n = items.length;
      items.forEach(it => {
        if (typeof it === 'object' && it.md) {
          const w = n === 1 ? it.width : it.width;
          pos['MARKDOWN-' + it.id] = { type: 'MARKDOWN', id: 'MARKDOWN-' + it.id, children: [], parents: [...tp, rid], meta: { width: w, height: it.height, code: it.code } };
          pos[rid].children.push('MARKDOWN-' + it.id);
        } else {
          const cid = itemId(it), ch = charts.find(c => c.id === cid);
          const isKpi = ch.params.viz_type === 'big_number_total';
          pos['CHART-' + cid] = { type: 'CHART', id: 'CHART-' + cid, children: [], parents: [...tp, rid], meta: { width: it.w || widthsFor(n), height: it.h || (isKpi ? 20 : (ch.params.viz_type === 'table' ? 48 : 52)), chartId: cid, uuid: uuid('chart' + ch.name), sliceName: ch.name } };
          pos[rid].children.push('CHART-' + cid);
        }
      });
    });
  });
  return pos;
}

// ───────────────────────── Escrita do pacote ─────────────────────────
function write(rel, obj) { const f = path.join(OUT, ROOT, rel); fs.mkdirSync(path.dirname(f), { recursive: true }); fs.writeFileSync(f, JSON.stringify(obj, null, 1), 'utf8'); }

fs.rmSync(path.join(OUT, ROOT), { recursive: true, force: true });
write('metadata.yaml', { version: '1.0.0', type: 'Dashboard', timestamp: new Date().toISOString() });
write('databases/Warehouse_gold.yaml', { database_name: DB.name, sqlalchemy_uri: DB_URI, cache_timeout: null, expose_in_sqllab: true, allow_run_async: false, allow_ctas: false, allow_cvas: false, allow_dml: false, allow_file_upload: false, extra: { allows_virtual_table_explore: true }, uuid: DB.uuid, version: '1.0.0' });
for (const [k, d] of Object.entries(DATASETS)) {
  write(`datasets/Warehouse_gold/${k}.yaml`, {
    table_name: k, main_dttm_col: null, description: d.desc, default_endpoint: null, offset: 0, cache_timeout: null, schema: 'gold', sql: null, params: null, template_params: null, filter_select_enabled: true, fetch_values_predicate: null, extra: null, normalize_columns: false, always_filter_main_dttm: false, uuid: d.uuid,
    metrics: d.metrics.map(x => ({ metric_name: x.name, verbose_name: x.verbose, metric_type: null, expression: x.expr, description: x.d || null, d3format: x.fmt, currency: null, extra: null, warning_text: null })),
    columns: d.cols.map(c => ({ column_name: c.n, verbose_name: c.d || null, is_dttm: false, is_active: true, type: c.t, advanced_data_type: null, groupby: true, filterable: true, expression: c.expr || null, description: null, python_date_format: null, extra: null })),
    version: '1.0.0', database_uuid: DB.uuid,
  });
}
charts.forEach(c => {
  write(`charts/${c.name.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^A-Za-z0-9]+/g, '_')}_${c.id}.yaml`, { slice_name: c.name, description: c.desc || null, certified_by: null, certification_details: null, viz_type: c.params.viz_type, params: c.params, query_context: null, cache_timeout: null, uuid: uuid('chart' + c.name), version: '1.0.0', dataset_uuid: ds(c.ds).uuid });
});
const meta = {
  color_scheme: 'univag', label_colors: LABELS, shared_label_colors: {}, map_label_colors: {}, refresh_frequency: 0, timed_refresh_immune_slices: [], expanded_slices: {}, cross_filters_enabled: true, default_filters: '{}', filter_scopes: {}, filter_bar_orientation: 'HORIZONTAL', chart_configuration: crossFilterConfig(),
  native_filter_configuration: nativeFilters(), global_chart_configuration: { scope: { rootPath: ['ROOT_ID'], excluded: [] }, chartsInScope: [] },
};
const css = `@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
body,body *:not(i):not(.fa):not([class*="fa-"]):not(code):not(pre){font-family:Roboto,'Segoe UI',system-ui,-apple-system,Arial,sans-serif!important}
body,.dashboard{background:#F8F9FA}
#main-menu{display:none}
.dashboard-header-container,.dashboard-header-container .header-with-actions{background:#1A2B5E!important}
.dashboard-header-container{border-radius:0 0 8px 8px;margin-bottom:0}
.chart-slice[data-test-viz-type="handlebars"]>div:first-child{display:none}
.dashboard-header-container .header-title,.dashboard-header-container .dynamic-title,.dashboard-header-container .input-sizer,.dashboard-header-container .editable-title input{color:#fff!important;font-weight:700}
.dashboard-header-container .anticon,.dashboard-header-container .anticon svg{color:#DEE2E6}
.dashboard-component-tabs .ant-tabs-tab-btn{color:#495057;font-weight:500}
.dashboard-component-tabs .ant-tabs-tab-active .ant-tabs-tab-btn{color:#1A2B5E;font-weight:700}
.dashboard-component-tabs .ant-tabs-ink-bar{background:#1A2B5E}
.dashboard-component-chart-holder{background:#fff;border:1px solid #DEE2E6;border-radius:8px;box-shadow:0 1px 3px rgba(26,43,94,.08)}
.dashboard-component-chart-holder:has([data-test-viz-type="handlebars"]){background:transparent!important;border:0!important;box-shadow:none!important}
.dashboard-markdown h3{color:#1A2B5E;margin-top:4px}
.dashboard-markdown blockquote{border-left:4px solid #1A2B5E;background:#EEF0F5;padding:6px 12px;color:#1A2B5E}
.dashboard-markdown .markdown{padding:6px 10px 4px;line-height:1.6;color:#343A40;font-size:14px}
.dashboard-markdown h3{font-size:20px;font-weight:700;margin:0 0 10px;padding-bottom:8px;border-bottom:2px solid #E9ECEF}
.dashboard-markdown h4{font-size:16px;font-weight:700;color:#1A2B5E;margin:0 0 8px;padding-left:10px;border-left:4px solid #1A2B5E;line-height:1.3}
.dashboard-markdown p{margin:0 0 10px}
.dashboard-markdown p>em:only-child{display:block;font-size:12.5px;font-style:normal;color:#6C757D;background:#F1F3F5;border-radius:6px;padding:6px 10px;margin-top:4px}
.dashboard-markdown ul{list-style:none;padding:0;margin:0;column-count:2;column-gap:40px}
.dashboard-markdown li{break-inside:avoid}
.dashboard-markdown li{position:relative;padding:5px 0 5px 18px;border-bottom:1px solid #F1F3F5}
.dashboard-markdown li:last-child{border-bottom:0}
.dashboard-markdown li:before{content:"";position:absolute;left:2px;top:13px;width:7px;height:7px;border-radius:50%;background:#1A2B5E}
.dashboard-markdown table{width:100%;border-collapse:collapse;margin:0 0 12px}
.dashboard-markdown th{text-align:left;font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;color:#6C757D;font-weight:700;padding:6px 14px 6px 0;border-bottom:2px solid #DEE2E6}
.dashboard-markdown td{padding:8px 14px 8px 0;border-bottom:1px solid #F1F3F5;vertical-align:top}
.dashboard-markdown td:last-child,.dashboard-markdown th:last-child{padding-right:0;white-space:nowrap}
.dashboard-markdown td:nth-child(2),.dashboard-markdown th:nth-child(2){white-space:nowrap}
.dashboard-markdown code{background:#EEF0F5;color:#1A2B5E;border-radius:4px;padding:1px 5px;font-size:12.5px}
.kpi{height:100%;box-sizing:border-box;background:#fff;border:1px solid #DEE2E6;border-radius:8px;padding:6px 14px;display:flex;flex-direction:column;justify-content:center;box-shadow:0 1px 3px rgba(26,43,94,.08)}
.kpi-l{font-size:12.5px;font-weight:500;color:#495057;line-height:1.2}
.kpi-v{font-size:32px;font-weight:700;color:#1A2B5E;line-height:1.1}
.kpi-s{font-size:11.5px;color:#495057;line-height:1.3;display:flex;flex-wrap:wrap;align-items:center;gap:2px 6px}
.kpi-hero{background:#1A2B5E;border-color:#1A2B5E}
.kpi-hero .kpi-l,.kpi-hero .kpi-v{color:#fff}
.kpi-hero .kpi-s{color:#DEE2E6}
.chip{display:inline-block;font-size:11px;font-weight:600;border-radius:10px;padding:0 7px}
.chip:empty{display:none}
.chip-n{background:#E9ECEF;color:#495057}
.chip-bad{background:#FFEBEE;color:#B71C1C}
.chip-good{background:#EAF6EC;color:#1B5E20}`;
write('dashboards/Rota_do_Diploma.yaml', { dashboard_title: 'Rota do Diploma · Mato Grosso', description: 'Trajetória e evasão no Ensino Superior de MT (INEP/IBGE). DataHack UNIVAG 2026.', css, slug: 'rota-do-diploma', certified_by: null, certification_details: null, published: true, uuid: uuid('dashboard'), position: buildPosition(), metadata: meta, version: '1.0.0' });

// ───────────────────────── Contrato das planilhas (Plano B, sem banco) ─────────────────────────
// Mesma lista de colunas físicas dos datasets: é o que docker/planilhas.py espera achar nas planilhas.
const TIPO_PT = { TEXT: 'texto', BIGINT: 'inteiro', NUMERIC: 'número', BOOLEAN: 'verdadeiro/falso', TIMESTAMP: 'data e hora' };
const contrato = { gerado_por: 'superset/build_bundle.js', tabelas: {} };
for (const [k, d] of Object.entries(DATASETS)) {
  contrato.tabelas[k] = { descricao: d.desc, colunas: d.cols.filter(c => !c.expr).map(c => ({ nome: c.n, tipo: c.t, rotulo: c.d || '' })) };
}
fs.writeFileSync(path.join(OUT, 'contrato_planilhas.json'), JSON.stringify(contrato, null, 1), 'utf8');
const md_contrato = ['# Contrato das planilhas (Plano B)', '',
  '> Gerado por `superset/build_bundle.js`; não edite à mão. Uma tabela = um arquivo (ou uma aba) com o nome abaixo.',
  '> Regras de nomes, formatos aceitos e como carregar: `superset/planilhas/LEIA-ME.md`.', ''];
for (const [k, t] of Object.entries(contrato.tabelas)) {
  md_contrato.push(`## ${k}`, '', t.descricao, '', '| Coluna | Tipo | Rótulo no dashboard |', '|---|---|---|');
  t.colunas.forEach(c => md_contrato.push(`| \`${c.nome}\` | ${TIPO_PT[c.tipo] || c.tipo} | ${c.rotulo} |`));
  md_contrato.push('');
}
fs.mkdirSync(path.join(__dirname, 'planilhas'), { recursive: true });
fs.writeFileSync(path.join(__dirname, 'planilhas', 'CONTRATO.md'), md_contrato.join('\n'), 'utf8');

const zip = path.join(OUT, 'rota_do_diploma.zip');
fs.rmSync(zip, { force: true });
const TAR = path.join(process.env.SystemRoot || 'C:/Windows', 'System32', 'tar.exe');
cp.execFileSync(TAR, ['-a', '-c', '-f', 'rota_do_diploma.zip', ROOT], { cwd: OUT, stdio: 'inherit' });
console.log(`OK ${charts.length} gráficos · ${Object.keys(DATASETS).length} datasets · ${tabs.length} abas · ${FILTERS.length} filtros -> ${zip}${DEMO ? ' (DEMO)' : ''}`);
