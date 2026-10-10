#!/usr/bin/env node
// Gera bundle/rota_do_diploma.zip (pacote de importação do Apache Superset 4.x).
//   node build_bundle.js            -> dashboard para os dados reais
//   node build_bundle.js --demo     -> idem, com faixa "DADOS DEMONSTRATIVOS" no topo
// UUIDs são derivados dos nomes: reimportar SOBRESCREVE (idempotente), não duplica.
const fs = require('fs'), path = require('path'), crypto = require('crypto'), cp = require('child_process');
const DEMO = process.argv.includes('--demo');
const DB_URI = process.env.ROTA_DB_URI || 'postgresql+psycopg2://rota:rota@db:5432/rota';
const OUT = path.join(__dirname, 'bundle'), ROOT = 'dashboard_export_rota_do_diploma';

const uuid = s => { const h = crypto.createHash('md5').update('rota|' + s).digest('hex'); return `${h.slice(0,8)}-${h.slice(8,12)}-4${h.slice(13,16)}-a${h.slice(17,20)}-${h.slice(20,32)}`; };

// ───────────────────────── Paleta UNIVAG (guia de estilos v1.1) ─────────────────────────
const C = { concl: '#0066CC', saiu: '#E83E8C', curso: '#6C757D', navy: '#1A2B5E', ciano: '#00AEF0', roxo: '#6F42C1' };

// ───────────────────────── Banco e datasets ─────────────────────────
const DB = { name: 'Rota do Diploma (mart)', uuid: uuid('db') };
const T = (n, t = 'TEXT', d = '') => ({ n, t, d });
const m = (name, verbose, expr, fmt = ',d', d = '') => ({ name, verbose, expr, fmt, d });
const PCT = (num, den) => `100.0 * SUM(${num}) / NULLIF(SUM(${den}), 0)`;
const COMMON = [T('categoria_adm'), T('rede'), T('modalidade'), T('area_cine', 'TEXT', 'Área geral CINE'), T('rotulo_cine', 'TEXT', 'Curso (rótulo CINE)'), T('co_municipio'), T('municipio'), T('co_ies'), T('no_ies', 'TEXT', 'Instituição'), T('co_curso'), T('no_curso', 'TEXT', 'Nome do curso'), T('grau')];
const DATASETS = {
  trajetoria: { desc: 'Indicadores de Trajetória (INEP). Grão: curso × coorte × ano de referência. Taxas ponderadas pelos ingressantes.',
    cols: [T('coorte', 'INTEGER', 'Coorte (ano de ingresso)'), T('ano_ref', 'INTEGER', 'Ano de referência'), T('ano_curso', 'INTEGER', 'Ano do curso'), T('qt_ingressante', 'INTEGER'), T('tda', 'NUMERIC'), T('tca', 'NUMERIC'), T('tap', 'NUMERIC'), T('tada', 'NUMERIC'), T('tcan', 'NUMERIC'), T('n_desist', 'NUMERIC'), T('n_concl', 'NUMERIC'), T('n_perm', 'NUMERIC'), T('n_desist_ano', 'NUMERIC'), ...COMMON],
    metrics: [m('ingressantes', 'Ingressantes', 'SUM(qt_ingressante)'), m('Concluíram', 'Concluíram', PCT('n_concl', 'qt_ingressante'), '.1f'), m('Saíram do curso', 'Saíram do curso', PCT('n_desist', 'qt_ingressante'), '.1f'),
      m('Em curso', 'Em curso', PCT('n_perm', 'qt_ingressante'), '.1f'), m('Saídas no ano', 'Saídas no ano', PCT('n_desist_ano', 'qt_ingressante'), '.1f'), m('n_cursos', 'Cursos', 'COUNT(DISTINCT co_curso)'), m('desistentes', 'Saíram do curso (alunos)', 'ROUND(SUM(n_desist))')] },
  censo_curso: { desc: 'Censo da Educação Superior, graduação em MT. Grão: ano × curso × município de oferta (EAD = polo).',
    cols: [T('ano', 'INTEGER', 'Ano do Censo'), T('qt_vagas', 'INTEGER'), T('qt_ing', 'INTEGER'), T('qt_mat', 'INTEGER'), T('qt_conc', 'INTEGER'), T('qt_desvinculado', 'INTEGER'), T('qt_transferido', 'INTEGER'), T('qt_trancada', 'INTEGER'), T('qt_falecido', 'INTEGER'), T('qt_ing_fies', 'INTEGER'), T('qt_ing_prouni', 'INTEGER'), T('qt_mat_fies', 'INTEGER'), T('qt_mat_prouni', 'INTEGER'), ...COMMON],
    metrics: [m('evasao_anual', 'Evasão anual (%)', PCT('qt_desvinculado', 'qt_mat + qt_desvinculado + qt_transferido'), '.1f'), m('matriculas', 'Matrículas', 'SUM(qt_mat)'), m('base_evasao', 'Base da evasão', 'SUM(qt_mat + qt_desvinculado + qt_transferido)'),
      m('desvinculados', 'Desvinculados', 'SUM(qt_desvinculado)'), m('ingressantes', 'Ingressantes', 'SUM(qt_ing)'), m('n_cursos', 'Cursos', 'COUNT(DISTINCT co_curso)')] },
  cpc_curso: { desc: 'CPC (2021–2023) ligado à Trajetória pela chave CO_CURSO. CPC do ano Y ↔ coorte Y−3, 4º ano do curso.',
    cols: [T('ano_cpc', 'INTEGER', 'Edição do CPC'), T('coorte_cpc', 'INTEGER', 'Coorte comparada (ano do CPC − 3)'), T('area_avaliacao', 'TEXT', 'Área de avaliação (Enade)'), T('cpc_faixa', 'TEXT', 'CPC (faixa)'), T('cpc_continuo', 'NUMERIC', 'CPC (contínuo)'), T('qt_ingressante', 'INTEGER'), T('n_desist', 'NUMERIC'), T('tda', 'NUMERIC'), ...COMMON.filter(c => ['categoria_adm', 'rede', 'modalidade', 'area_cine', 'municipio', 'no_ies', 'co_curso', 'no_curso'].includes(c.n))],
    metrics: [m('Saíram do curso', 'Saíram do curso em 4 anos (%)', PCT('n_desist', 'qt_ingressante'), '.1f'), m('ingressantes', 'Ingressantes', 'SUM(qt_ingressante)'), m('n_cursos', 'Cursos', 'COUNT(DISTINCT co_curso)'),
      m('cpc_medio', 'CPC médio', 'AVG(cpc_continuo)', '.2f'), m('desistentes', 'Saíram do curso (alunos)', 'ROUND(SUM(n_desist))')] },
  licenciatura_curso: { desc: 'Licenciaturas de MT: coorte 2015 em 2024 + Conceito Enade 2025 (padrão de proficiência).',
    cols: [T('coorte_ref', 'INTEGER'), T('area_avaliacao', 'TEXT', 'Área de avaliação'), T('qt_ingressante', 'INTEGER'), T('n_desist', 'NUMERIC'), T('tda', 'NUMERIC'), T('participantes', 'INTEGER'), T('n_padrao', 'INTEGER'), T('pct_padrao', 'NUMERIC'), T('conceito_faixa', 'TEXT'), ...COMMON.filter(c => ['categoria_adm', 'rede', 'modalidade', 'municipio', 'no_ies', 'co_curso', 'no_curso'].includes(c.n))],
    metrics: [m('Saíram do curso', 'Saíram do curso (%)', PCT('n_desist', 'qt_ingressante'), '.1f'), m('pct_padrao_agr', 'No padrão de proficiência ou acima (%)', PCT('n_padrao', 'participantes'), '.1f'), m('ingressantes', 'Ingressantes', 'SUM(qt_ingressante)'),
      m('participantes_enade', 'Concluintes participantes', 'SUM(participantes)'), m('n_cursos', 'Cursos', 'COUNT(DISTINCT co_curso)')] },
  oferta_municipio: { desc: 'Vagas presenciais (Censo 2024) por 100 jovens de 18–24 anos (IBGE 2022). Os 142 municípios de MT; zero = sem oferta.',
    cols: [T('co_municipio'), T('municipio'), T('vagas_pres', 'INTEGER'), T('vagas_pres_pub', 'INTEGER'), T('vagas_pres_priv', 'INTEGER'), T('pop_18_24', 'INTEGER'), T('vagas_por_100', 'NUMERIC'), T('faixa_oferta', 'TEXT', 'Faixa de oferta')],
    metrics: [m('vagas_100', 'Vagas por 100 jovens', '100.0 * SUM(vagas_pres) / NULLIF(SUM(pop_18_24), 0)', '.1f'), m('vagas', 'Vagas presenciais', 'SUM(vagas_pres)'), m('jovens', 'Jovens de 18 a 24 anos', 'SUM(pop_18_24)'),
      m('n_municipios', 'Municípios', 'COUNT(*)'), m('n_sem_oferta', 'Municípios sem oferta presencial', 'SUM(CASE WHEN vagas_pres = 0 THEN 1 ELSE 0 END)')] },
  financiamento_curso: { desc: 'FIES e ProUni entre os ingressantes da rede privada (graduação, MT). Grão: ano × curso.',
    cols: [T('ano', 'INTEGER', 'Ano do Censo'), T('qt_ing', 'INTEGER'), T('qt_ing_fies', 'INTEGER'), T('qt_ing_prouni', 'INTEGER'), T('qt_mat', 'INTEGER'), T('qt_mat_fies', 'INTEGER'), T('qt_mat_prouni', 'INTEGER'), T('qt_desvinculado', 'INTEGER'), T('qt_transferido', 'INTEGER'), T('faixa_fies', 'TEXT', '% de ingressantes com FIES'), T('faixa_prouni', 'TEXT', '% de ingressantes com ProUni'),
      T('categoria_adm'), T('modalidade'), T('area_cine', 'TEXT', 'Área geral CINE'), T('no_ies', 'TEXT', 'Instituição'), T('co_curso'), T('no_curso')],
    metrics: [m('pct_fies_ing', 'FIES (% dos ingressantes)', PCT('qt_ing_fies', 'qt_ing'), '.1f'), m('pct_prouni_ing', 'ProUni (% dos ingressantes)', PCT('qt_ing_prouni', 'qt_ing'), '.1f'), m('pct_fies_mat', 'FIES (% dos matriculados)', PCT('qt_mat_fies', 'qt_mat'), '.1f'),
      m('pct_prouni_mat', 'ProUni (% dos matriculados)', PCT('qt_mat_prouni', 'qt_mat'), '.1f'), m('evasao_anual', 'Evasão anual (%)', PCT('qt_desvinculado', 'qt_mat + qt_desvinculado + qt_transferido'), '.1f'), m('base_evasao', 'Base da evasão', 'SUM(qt_mat + qt_desvinculado + qt_transferido)'),
      m('n_cursos', 'Cursos', 'COUNT(DISTINCT co_curso)'), m('ingressantes', 'Ingressantes', 'SUM(qt_ing)')] },
  qualidade_checks: { desc: 'Checagens automáticas da transformação (staging → mart).', cols: [T('etapa'), T('checagem'), T('valor', 'NUMERIC'), T('esperado'), T('ok', 'BOOLEAN')], metrics: [] },
};
Object.values(DATASETS).forEach((d, i) => { d.uuid = uuid('ds' + Object.keys(DATASETS)[i]); });
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
const LABELS = { 'Concluíram': C.concl, 'Saíram do curso': C.saiu, 'Em curso': C.curso, 'Saídas no ano': C.saiu };

function kpi(name, dsKey, metric, fmt, sub, filters, desc) {
  return add(name, dsKey, { viz_type: 'big_number_total', metric, subheader: sub, y_axis_format: fmt, header_font_size: 0.6, subheader_font_size: 0.2, adhoc_filters: filters, color_picker: { r: 26, g: 43, b: 94, a: 1 }, force_timestamp_formatting: false }, desc);
}
function bar(name, dsKey, o, desc) {
  const horiz = o.horizontal;
  return add(name, dsKey, Object.assign({
    viz_type: 'echarts_timeseries_bar', x_axis: o.x, xAxisForceCategorical: true, metrics: o.metrics, groupby: o.groupby || [], adhoc_filters: o.filters || [],
    orientation: horiz ? 'horizontal' : 'vertical', stack: o.stack || null, show_value: o.showValue !== false, show_legend: !!(o.groupby && o.groupby.length) || o.metrics.length > 1,
    legendType: 'scroll', legendOrientation: 'top', row_limit: o.limit || 1000, order_desc: true, color_scheme: 'univag', rich_tooltip: true, showTooltipTotal: !!o.stack,
    y_axis_format: o.fmt || '.1f', y_axis_title: o.yTitle || '', y_axis_title_margin: 40, x_axis_title: o.xTitle || '', x_axis_title_margin: 30, truncateYAxis: false, zoomable: false, minorTicks: false,
    x_axis_sort: o.sortBy || null, x_axis_sort_asc: o.sortAsc === true, sort_series_type: 'sum', sort_series_ascending: false, xAxisLabelRotation: 0, only_total: true, show_extra_controls: false, markerEnabled: false, forecastEnabled: false,
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
function md(id, code, width = 12, height = 12) { return { md: true, id, code, width, height }; }

// ───────────────────────── Texto ─────────────────────────
const SRC_TRAJ = 'INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024).';
const SRC_CENSO = 'INEP, Censo da Educação Superior (cursos), 2021–2024.';
const HOW_PCT = 'Percentual = alunos na situação ÷ ingressantes, ponderado pelo nº de ingressantes de cada curso (não é média simples de taxas). Grupos com menos de 10 alunos não aparecem.';
const WHERE_P1 = ' Filtro fixo: cursos presenciais. Use o filtro "Coorte" (barra à esquerda).';

// ───────────────────────── Montagem dos gráficos por aba ─────────────────────────
const P = 'ano_ref';
const fixP1 = [eq('modalidade', 'Presencial')];                  // P1/P2: só presencial (regra do desafio)
const fix2024 = [...fixP1, eq('ano_ref', 2024)];
const tabs = [];  // {id, title, rows:[[item...]]}   item = chartId | md(...)

function kpiRowP1(tag) {
  return [
    kpi(`${tag} · Concluíram (%)`, 'trajetoria', 'Concluíram', '.1f', '% dos ingressantes da coorte · situação em 2024', [...fix2024, K10('qt_ingressante')], 'TCA ponderada. ' + HOW_PCT + ' Fonte: ' + SRC_TRAJ + WHERE_P1),
    kpi(`${tag} · Saíram do curso (%)`, 'trajetoria', 'Saíram do curso', '.1f', '% dos ingressantes · inclui transferências · situação em 2024', [...fix2024, K10('qt_ingressante')], 'TDA ponderada. "Saíram do curso" não significa necessariamente abandono da graduação. ' + HOW_PCT + ' Fonte: ' + SRC_TRAJ + WHERE_P1),
    kpi(`${tag} · Em curso (%)`, 'trajetoria', 'Em curso', '.1f', '% dos ingressantes · cursando ou trancado · situação em 2024', [...fix2024, K10('qt_ingressante')], 'TAP ponderada. ' + HOW_PCT + ' Fonte: ' + SRC_TRAJ + WHERE_P1),
    kpi(`${tag} · Total de ingressantes`, 'trajetoria', 'ingressantes', ',d', 'ingressantes presenciais da coorte', [...fix2024, K10('qt_ingressante')], 'Soma de QT_INGRESSANTE dos cursos presenciais de MT na coorte.' + ' Fonte: ' + SRC_TRAJ),
  ];
}
function evolution(tag) {
  return bar(`${tag} · Situação da coorte ao fim de cada ano`, 'trajetoria', { x: P, metrics: ['Concluíram', 'Saíram do curso', 'Em curso'], stack: 'Stack', filters: [...fixP1, K10('qt_ingressante')], fmt: '.1f', yTitle: '% dos ingressantes', xTitle: 'Ano de referência', showValue: false },
    'Cada coluna soma 100%: concluíram + saíram do curso + em curso, acumulado até o ano. ' + HOW_PCT + WHERE_P1 + ' Fonte: ' + SRC_TRAJ);
}
function lossYear(tag) {
  return bar(`${tag} · Em que ano do curso a perda é maior?`, 'trajetoria', { x: 'ano_curso', metrics: ['Saídas no ano'], filters: [...fixP1, K10('qt_ingressante')], fmt: '.1f', yTitle: 'p.p. da coorte que saíram no ano', xTitle: 'Ano do curso (1º = ano de ingresso)', extra: { color_scheme: 'univag' } },
    'Saídas ocorridas em cada ano do curso, em pontos percentuais da coorte (TADA ponderada). A barra mais alta é o ano de maior perda. ' + WHERE_P1 + ' Fonte: ' + SRC_TRAJ);
}
function top5(tag, limit, menor) {
  return bar(`${tag} · Cursos com ${menor ? 'menor' : 'maior'} desistência após o ano do curso escolhido`, 'trajetoria', { x: 'rotulo_cine', metrics: ['Saíram do curso'], limit, sortBy: 'Saíram do curso', sortAsc: !!menor, filters: [...fixP1, K10('qt_ingressante'), having('SUM(n_desist) >= 10')], fmt: '.1f', yTitle: '% que saiu do curso', extra: { xAxisLabelRotation: 45 } },
    'Cursos (rótulo CINE) ordenados pela desistência acumulada, no ano do curso escolhido (filtro "Ano do curso"). Cursos com menos de 10 ingressantes ou desistentes não aparecem. ' + WHERE_P1 + ' Fonte: ' + SRC_TRAJ);
}
function p3line(tag) {
  return line(`${tag} · Evasão anual por categoria e modalidade`, 'censo_curso', { x: 'ano', metrics: ['evasao_anual'], groupby: ['categoria_adm', 'modalidade'], filters: [having('SUM(qt_mat + qt_desvinculado + qt_transferido) >= 10')], yTitle: 'Evasão anual (%)', xTitle: 'Ano do Censo', showValue: false },
    'Evasão anual (proxy do Censo) = desvinculados ÷ (matriculados + desvinculados + transferidos), no ano. Mede a perda DAQUELE ano, não a da turma inteira. Fonte: ' + SRC_CENSO);
}
function cpcBars(tag) {
  return bar(`${tag} · Desistência por faixa do CPC`, 'cpc_curso', { x: 'cpc_faixa', metrics: ['Saíram do curso'], sortBy: null, filters: [K10('qt_ingressante'), having('SUM(n_desist) >= 10')], fmt: '.1f', yTitle: '% que saiu do curso em 4 anos', xTitle: 'CPC (faixa)', extra: { x_axis_sort_series: 'name' } },
    'Desistência em 4 anos (coorte Y−3 → situação em Y) por faixa do CPC da edição Y, ponderada pelos ingressantes. "Sem conceito" não é nota zero: fica de fora da comparação. Associação observada, não causa. Fonte: INEP, CPC 2021–2023 + Trajetória.');
}

// ── Visão geral
tabs.push({ id: 'overview', title: 'Visão geral', rows: [
  [md('md-ov', `### Rota do Diploma · Mato Grosso\nDe cada 100 estudantes que entram numa graduação presencial em MT, quantos chegam ao diploma? Os números abaixo seguem os **filtros da barra à esquerda** (coorte de ingresso, rede, área, município…). Associação, não causa: dados agregados por curso e município.`, 12, 14)],
  kpiRowP1('Visão geral'),
  [evolution('Visão geral'), top5('Visão geral', 5)],
  [p3line('Visão geral'), cpcBars('Visão geral')],
] });

// ── P1
tabs.push({ id: 'p1', title: 'P1 · Trajetória', rows: [
  [md('md-p1', `### P1 · Quanto da turma fica pelo caminho?\nDos ingressantes de **2015** nos cursos presenciais de MT: que percentual **concluiu**, **saiu do curso** e **ainda estava no curso** em 2024? Em que ano do curso a perda é maior?\n*Use o filtro **Coorte** para comparar outras turmas.*`, 12, 15)],
  kpiRowP1('P1'),
  [evolution('P1'), lossYear('P1')],
  [table('P1 · Bases de cálculo por ano', 'trajetoria', { groupby: ['ano_ref'], metrics: ['Concluíram', 'Saíram do curso', 'Em curso', 'Saídas no ano', 'ingressantes'], filters: [...fixP1, K10('qt_ingressante')], sortMetric: null, desc: false, orderRaw: null, page: 12 },
    'Mesmos números do gráfico, em tabela, com a base (ingressantes). ' + HOW_PCT + WHERE_P1 + ' Fonte: ' + SRC_TRAJ)],
] });

// ── P2
const p2Hm = heat('P2 · Rótulo × coorte no mesmo ano do curso', 'trajetoria', { x: 'coorte', y: 'rotulo_cine', metric: 'Saíram do curso', filters: [...fixP1, K10('qt_ingressante'), having('SUM(n_desist) >= 10')], limit: 5000 },
  'Compara COORTES diferentes no MESMO ano do curso (filtro "Ano do curso"), nunca na mesma data. Cada célula é a desistência acumulada ponderada do curso naquela coorte. Células com menos de 10 ingressantes/desistentes não aparecem. Fonte: ' + SRC_TRAJ);
tabs.push({ id: 'p2', title: 'P2 · Cursos e áreas', rows: [
  [md('md-p2', `### P2 · Onde a rota mais se perde?\nCursos (rótulo CINE) e áreas com **maior** e **menor** desistência acumulada em MT, no **mesmo ano do curso**. A matriz abaixo compara coortes 2015–2020 lado a lado.\n*Escolha o **Ano do curso** e a **Coorte** nos filtros.*`, 12, 15)],
  [top5('P2', 10), top5('P2', 10, true)],
  [bar('P2 · Desistência por área geral (CINE)', 'trajetoria', { x: 'area_cine', metrics: ['Saíram do curso'], horizontal: true, sortBy: 'Saíram do curso', sortAsc: true, filters: [...fixP1, K10('qt_ingressante'), having('SUM(n_desist) >= 10')], fmt: '.1f', yTitle: '% que saiu do curso', extra: { y_axis_title_margin: 30 } },
     'Áreas gerais CINE ordenadas pela desistência acumulada ponderada, no ano do curso escolhido. ' + WHERE_P1 + ' Fonte: ' + SRC_TRAJ),
   table('P2 · Bases de cálculo por curso', 'trajetoria', { groupby: ['rotulo_cine'], metrics: ['Saíram do curso', 'desistentes', 'ingressantes'], filters: [...fixP1, K10('qt_ingressante'), having('SUM(n_desist) >= 10')], sortMetric: 'Saíram do curso', desc: true, page: 15 },
    'Numerador (saíram do curso), denominador (ingressantes) e taxa por curso. ' + WHERE_P1 + ' Fonte: ' + SRC_TRAJ)],
  [p2Hm],
] });

// ── P3
const H3 = having('SUM(qt_mat + qt_desvinculado + qt_transferido) >= 10');
tabs.push({ id: 'p3', title: 'P3 · Rede e modalidade', rows: [
  [md('md-p3', `### P3 · Pública × privada, presencial × EAD\nComo a **evasão anual** e a **distribuição das matrículas** variam entre rede pública e privada (com e sem fins lucrativos) e entre presencial e EAD, de **2021 a 2024**? Há algum **ano atípico**?\n> **Evasão anual (Censo) ≠ desistência acumulada (Trajetória).** Aqui a medida é a perda de um único ano. No EAD, o município é o do **polo**, não o do aluno.`, 12, 19)],
  [p3line('P3'),
   bar('P3 · Distribuição das matrículas', 'censo_curso', { x: 'ano', metrics: ['matriculas'], groupby: ['categoria_adm', 'modalidade'], stack: 'Expand', filters: [], fmt: '.0%', yTitle: '% das matrículas', xTitle: 'Ano do Censo', showValue: false },
     'Participação de cada categoria × modalidade no total de matrículas do ano (colunas somam 100%). Fonte: ' + SRC_CENSO)],
  [pivot('P3 · Matrículas por ano (procure saltos)', 'censo_curso', { rows: ['categoria_adm', 'modalidade'], cols: ['ano'], metrics: ['matriculas'], fmt: ',d', filters: [] },
     'Matrículas por categoria administrativa e modalidade. Um valor que dispara num ano e volta ao normal pede investigação antes de virar conclusão (ex.: salto de 2023, possível mudança de coleta/cadastro). Fonte: ' + SRC_CENSO),
  ,table('P3 · Bases da evasão anual', 'censo_curso', { groupby: ['ano', 'rede', 'modalidade'], metrics: ['evasao_anual', 'desvinculados', 'base_evasao'], filters: [H3], desc: false, page: 12 },
     'Numerador (desvinculados) e denominador (matriculados + desvinculados + transferidos) por ano, rede e modalidade. Fonte: ' + SRC_CENSO)],
] });

// ── P4
tabs.push({ id: 'p4', title: 'P4 · CPC e desistência', rows: [
  [md('md-p4', `### P4 · Qualidade retém?\nCursos com **CPC mais alto** (ciclo 2021–2023) têm **desistência menor**? Mostre a relação e discuta o que mais pode explicá-la.\n> **Associação observada, não causa.** Cursos *sem conceito* (SC) ficam fora da comparação: ausência de nota **não** é zero. Rede, modalidade e área também diferem entre as faixas (veja os gráficos de controle).`, 12, 19)],
  [cpcBars('P4'),
   bubble('P4 · CPC contínuo × desistência (um ponto por curso)', 'cpc_curso', { entity: 'co_curso', x: { expressionType: 'SQL', sqlExpression: 'MAX(cpc_continuo)', label: 'CPC (contínuo)' }, y: { expressionType: 'SQL', sqlExpression: '100.0 * SUM(n_desist) / NULLIF(SUM(qt_ingressante), 0)', label: 'Saíram do curso (%)' }, size: { expressionType: 'SQL', sqlExpression: 'SUM(qt_ingressante)', label: 'Ingressantes' }, series: 'rede',
      filters: [sqlw("cpc_faixa <> 'Sem CPC'"), K10('qt_ingressante'), having('SUM(n_desist) >= 10')], xTitle: 'CPC (contínuo, 0–5)', yTitle: '% que saiu do curso em 4 anos', limit: 2000 },
      'Cada bolha é um curso (tamanho = ingressantes). Mostra a relação entre o CPC contínuo e a desistência em 4 anos; cores = rede. Cursos sem conceito e com menos de 10 ingressantes/desistentes não aparecem. Associação, não causa. Fonte: INEP, CPC 2021–2023 + Trajetória.')],
  [bar('P4 · Controle: faixa do CPC × rede', 'cpc_curso', { x: 'cpc_faixa', metrics: ['Saíram do curso'], groupby: ['rede'], filters: [K10('qt_ingressante'), having('SUM(n_desist) >= 10')], fmt: '.1f', yTitle: '% que saiu do curso', xTitle: 'CPC (faixa)' },
      'Mesma comparação separada por rede: se a relação some dentro de cada rede, a rede explica parte do efeito aparente.'),
   bar('P4 · Controle: faixa do CPC × modalidade', 'cpc_curso', { x: 'cpc_faixa', metrics: ['Saíram do curso'], groupby: ['modalidade'], filters: [K10('qt_ingressante'), having('SUM(n_desist) >= 10')], fmt: '.1f', yTitle: '% que saiu do curso', xTitle: 'CPC (faixa)' },
      'Mesma comparação separada por modalidade (presencial × EAD).')],
  [table('P4 · Cobertura e bases por faixa', 'cpc_curso', { groupby: ['cpc_faixa'], metrics: ['n_cursos', 'ingressantes', 'desistentes', 'Saíram do curso'], filters: [], desc: false, page: 8 },
      'Quantos cursos e ingressantes há em cada faixa, incluindo "Sem conceito" (cobertura). Taxa ponderada pelos ingressantes. Fonte: INEP, CPC 2021–2023 + Trajetória.')],
] });

// ── P5
const lic = [K10('qt_ingressante')];
tabs.push({ id: 'p5', title: 'P5 · Licenciaturas', rows: [
  [md('md-p5', `### P5 · O funil das licenciaturas\nNas licenciaturas de MT: quanto da turma **desiste** e quanto dos **concluintes atinge o padrão de proficiência** no Enade 2025? Quais áreas **formam pouco e com baixa proficiência**?\n> **Bases diferentes:** a desistência é da **coorte 2015** (Trajetória); a proficiência é de quem **concluiu e fez o Enade 2025**. Não são os mesmos estudantes.`, 12, 19)],
  [kpi('P5 · Ingressantes (coorte 2015)', 'licenciatura_curso', 'ingressantes', ',d', 'ingressantes em licenciaturas', lic, 'Soma de QT_INGRESSANTE das licenciaturas de MT, coorte 2015. Fonte: ' + SRC_TRAJ),
   kpi('P5 · Saíram do curso (%)', 'licenciatura_curso', 'Saíram do curso', '.1f', '% da coorte 2015 · situação em 2024', lic, 'TDA ponderada das licenciaturas. ' + HOW_PCT),
   kpi('P5 · Concluintes participantes (Enade 2025)', 'licenciatura_curso', 'participantes_enade', ',d', 'participantes', lic, 'Concluintes que fizeram a prova do Enade das Licenciaturas 2025.'),
   kpi('P5 · No padrão de proficiência ou acima (%)', 'licenciatura_curso', 'pct_padrao_agr', '.1f', '% dos concluintes participantes', [K10('participantes')], 'Percentual de concluintes igual ou acima do Padrão 1 de Proficiência (Enade 2025), ponderado pelos participantes. Fonte: INEP, Conceito Enade 2025 · Licenciaturas.')],
  [bar('P5 · Desistência por área (licenciaturas)', 'licenciatura_curso', { x: 'area_avaliacao', metrics: ['Saíram do curso'], horizontal: true, sortBy: 'Saíram do curso', sortAsc: true, filters: [...lic, having('SUM(n_desist) >= 10')], yTitle: '% que saiu do curso (coorte 2015)', extra: { y_axis_title_margin: 30 } },
      'Desistência acumulada da coorte 2015 por área de avaliação do Enade. Áreas com menos de 10 ingressantes/desistentes não aparecem. Fonte: ' + SRC_TRAJ),
   bar('P5 · Proficiência por área (Enade 2025)', 'licenciatura_curso', { x: 'area_avaliacao', metrics: ['pct_padrao_agr'], horizontal: true, sortBy: 'pct_padrao_agr', sortAsc: false, filters: [K10('participantes')], yTitle: '% no padrão de proficiência ou acima', extra: { y_axis_title_margin: 30 } },
      '% de concluintes participantes no padrão de proficiência ou acima, por área. Áreas com menos de 10 participantes não aparecem. Fonte: INEP, Conceito Enade 2025 · Licenciaturas.')],
  [bubble('P5 · Quem forma pouco e com baixa proficiência', 'licenciatura_curso', { entity: 'co_curso', series: 'area_avaliacao', x: { expressionType: 'SQL', sqlExpression: 'MAX(pct_padrao)', label: 'No padrão ou acima (%)' }, y: { expressionType: 'SQL', sqlExpression: 'MAX(tda)', label: 'Saíram do curso (%)' }, size: { expressionType: 'SQL', sqlExpression: 'SUM(participantes)', label: 'Concluintes participantes' },
      filters: [K10('qt_ingressante'), K10('participantes')], xTitle: '% dos concluintes no padrão de proficiência (quanto menor, pior)', yTitle: '% da coorte que saiu do curso (quanto maior, pior)' },
      'Cada bolha é um curso de licenciatura, colorido pela área. Canto superior-esquerdo = muita desistência e baixa proficiência. Tamanho = concluintes participantes (formam pouco = bolha pequena). Bases distintas: não são os mesmos estudantes.'),
   table('P5 · Bases de cálculo por área', 'licenciatura_curso', { groupby: ['area_avaliacao'], metrics: ['n_cursos', 'ingressantes', 'Saíram do curso', 'participantes_enade', 'pct_padrao_agr'], filters: [K10('qt_ingressante')], sortMetric: 'Saíram do curso', page: 10 },
      'Bases de cada medida. Desistência: coorte 2015. Proficiência: Enade 2025. Fonte: Trajetória + Enade Licenciaturas 2025.')],
] });

// ── B1
tabs.push({ id: 'b1', title: 'B1 · Desertos de ensino superior', rows: [
  [md('md-b1', `### B1 · Desertos de ensino superior\nQuantas **vagas presenciais** de graduação há para cada **100 jovens de 18–24 anos** em cada município de MT? Onde estão os municípios **sem oferta**?\n> Vagas presenciais do Censo 2024 ÷ população de 18–24 anos (IBGE, Censo 2022). **Zero é zero registrado** (município sem curso presencial), não ausência de dado. Município = local de oferta; EAD fica de fora.`, 12, 19)],
  [kpi('B1 · Vagas por 100 jovens (MT)', 'oferta_municipio', 'vagas_100', '.1f', 'vagas presenciais 2024 ÷ jovens de 18 a 24 anos', [], 'Soma das vagas ÷ soma da população dos municípios selecionados. Fonte: INEP, Censo da Educação Superior 2024; IBGE/SIDRA tabela 9514 (Censo 2022).'),
   kpi('B1 · Municípios sem oferta presencial', 'oferta_municipio', 'n_sem_oferta', ',d', 'municípios com zero vagas presenciais', [], 'Contagem de municípios com zero vagas presenciais em 2024.'),
   kpi('B1 · Municípios', 'oferta_municipio', 'n_municipios', ',d', 'municípios no recorte (MT tem 142)', [], 'Todos os municípios de MT vêm do IBGE; quem não tem curso entra com zero vagas.'),
   kpi('B1 · Vagas presenciais', 'oferta_municipio', 'vagas', ',d', 'vagas presenciais de graduação em 2024', [], 'Soma de QT_VG_TOTAL dos cursos presenciais.')],
  [bar('B1 · Municípios com maior oferta (vagas por 100 jovens)', 'oferta_municipio', { x: 'municipio', metrics: ['vagas_100'], limit: 15, sortBy: 'vagas_100', sortAsc: false, filters: [], yTitle: 'vagas presenciais por 100 jovens', extra: { xAxisLabelRotation: 45 } }, 'Os 15 municípios com mais vagas presenciais por 100 jovens de 18 a 24 anos.'),
   bar('B1 · Quantos municípios em cada faixa de oferta', 'oferta_municipio', { x: 'faixa_oferta', metrics: ['n_municipios'], fmt: ',d', filters: [], yTitle: 'municípios', xTitle: 'Faixa (vagas por 100 jovens)', extra: { x_axis_sort_series: 'name' } }, 'Distribuição dos municípios por faixa de vagas por 100 jovens. "Sem oferta" = zero vagas presenciais.')],
  [table('B1 · Maiores desertos (sem oferta, por população jovem)', 'oferta_municipio', { raw: true, columns: ['municipio', 'pop_18_24', 'vagas_pres', 'vagas_por_100'], filters: [eq('vagas_pres', 0)], orderRaw: ['pop_18_24', false], page: 12 },
      'Municípios sem nenhuma vaga presencial, ordenados pela população de 18 a 24 anos (onde há mais jovens sem oferta local).')],
] });

// ── B2
const HB2 = having('SUM(qt_ing) >= 10');
tabs.push({ id: 'b2', title: 'B2 · Financiamento', rows: [
  [md('md-b2', `### B2 · Financiamento e permanência\nQual o peso do **FIES** e do **ProUni** entre os ingressantes da rede **privada** de MT (2021–2024)? Cursos com **mais financiados evadem menos**?\n> Comparamos **cursos** agrupados pela faixa de participação do programa (dados agregados por curso, não por aluno). **Associação, não causa:** cursos com mais bolsistas diferem em área, modalidade e perfil.`, 12, 19)],
  [bar('B2 · Peso do FIES e do ProUni entre os ingressantes', 'financiamento_curso', { x: 'ano', metrics: ['pct_fies_ing', 'pct_prouni_ing'], filters: [HB2], yTitle: '% dos ingressantes da rede privada', xTitle: 'Ano do Censo' }, 'Participação de FIES e de ProUni (integral + parcial), separadamente, entre os ingressantes da rede privada. Os programas não são somados entre si. Fonte: ' + SRC_CENSO),
   bar('B2 · Peso do FIES e do ProUni entre os matriculados', 'financiamento_curso', { x: 'ano', metrics: ['pct_fies_mat', 'pct_prouni_mat'], filters: [having('SUM(qt_mat) >= 10')], yTitle: '% dos matriculados da rede privada', xTitle: 'Ano do Censo' }, 'Mesma leitura, agora sobre os matriculados. Fonte: ' + SRC_CENSO)],
  [bar('B2 · Evasão anual por faixa de FIES', 'financiamento_curso', { x: 'faixa_fies', metrics: ['evasao_anual'], groupby: ['ano'], filters: [having('SUM(qt_mat + qt_desvinculado + qt_transferido) >= 10')], yTitle: 'Evasão anual (%)', xTitle: '% de ingressantes do curso com FIES', extra: { x_axis_sort_series: 'name', sort_series_type: 'name', sort_series_ascending: true } }, 'Cursos agrupados pela participação de FIES entre seus ingressantes; evasão anual ponderada em cada faixa. Associação, não causa. Fonte: ' + SRC_CENSO),
   bar('B2 · Evasão anual por faixa de ProUni', 'financiamento_curso', { x: 'faixa_prouni', metrics: ['evasao_anual'], groupby: ['ano'], filters: [having('SUM(qt_mat + qt_desvinculado + qt_transferido) >= 10')], yTitle: 'Evasão anual (%)', xTitle: '% de ingressantes do curso com ProUni', extra: { x_axis_sort_series: 'name', sort_series_type: 'name', sort_series_ascending: true } }, 'Idem para ProUni. Associação, não causa. Fonte: ' + SRC_CENSO)],
  [table('B2 · Bases de cálculo por ano', 'financiamento_curso', { groupby: ['ano'], metrics: ['n_cursos', 'ingressantes', 'pct_fies_ing', 'pct_prouni_ing', 'evasao_anual'], filters: [HB2], desc: false, page: 6 }, 'Cursos, ingressantes e taxas por ano na rede privada. Fonte: ' + SRC_CENSO)],
] });

// ── Fontes e método
const METH = [
  ['Concluíram · Saíram do curso · Em curso', 'Situação dos ingressantes da coorte em 2024, no curso de ingresso. **Concluíram** = TCA; **Saíram do curso** = TDA (desvinculados e transferidos, não é necessariamente abandono da graduação); **Em curso** = TAP (cursando ou trancado). As três somam ≈100%.', 'Taxa = Σ(taxa × ingressantes) ÷ Σ ingressantes (média ponderada). Grupos com menos de 10 alunos são suprimidos.'],
  ['Desistência por curso e área', 'Desistência acumulada (TDA) no mesmo **ano do curso**, nunca na mesma data. Coortes diferentes só se comparam no mesmo horizonte.', 'Agrupamento por rótulo e área geral CINE. Ponderação pelos ingressantes.'],
  ['Evasão anual por rede e modalidade', 'Evasão anual (proxy do Censo) = **desvinculados ÷ (matriculados + desvinculados + transferidos)**, no ano. Mede o fluxo de um ano; **não se compara** à desistência acumulada de coorte.', 'Graduação em MT (CO_UF = 51). EAD aparece por polo: some alunos entre polos, conte cursos com COUNT(DISTINCT).'],
  ['CPC × desistência', 'CPC do ano Y comparado à coorte Y−3 no 4º ano do curso. Junção pela chave **CO_CURSO**. Cursos sem CPC ficam como "Sem conceito" (não é zero).', 'Taxa ponderada pelos ingressantes. Veja a taxa de junção na aba de qualidade abaixo. Associação, não causa.'],
  ['Licenciaturas · Enade 2025', 'Desistência da coorte 2015 (Trajetória) e % de concluintes no padrão de proficiência (Enade 2025), por área de avaliação. **Bases e denominadores distintos.**', 'Ligação apenas pelo curso (CO_CURSO), sem vínculo individual.'],
  ['Desertos · FIES e ProUni', 'Vagas presenciais ÷ jovens de 18–24 anos (Censo 2024 ÷ IBGE 2022); FIES e ProUni como % dos ingressantes/matriculados da rede privada.', 'Código IBGE do município de 7 dígitos. Fontes de anos diferentes; vagas não equivalem a matrículas.'],
];
tabs.push({ id: 'fontes', title: 'Fontes e metodologia', rows: [
  [md('md-fontes', `### Fontes de dados\n| Fonte | Edição | Usada em |\n|---|---|---|\n| INEP · Indicadores de Trajetória da Educação Superior | Coortes 2015–2020, até 2024 | P1, P2, P4, P5 |\n| INEP · Censo da Educação Superior (cursos) | 2021–2024 | P3, B1, B2 |\n| INEP · Conceito Preliminar de Curso (CPC) | 2021, 2022, 2023 | P4 |\n| INEP · Conceito Enade 2025 · Licenciaturas | 2025 | P5 |\n| IBGE/SIDRA · tabela 9514 (Censo Demográfico) | 2022 | B1 |\n\nSomente dados públicos. **Associação, não causa.** Grupos com menos de 10 alunos não são exibidos.${DEMO ? '\n\n**Os números desta versão são DEMONSTRATIVOS (sintéticos), sem validade oficial.**' : ''}`, 6, 34),
   md('md-glos', `### Definições\n- **Coorte**: turma que ingressou num curso num mesmo ano.\n- **TDA / TCA / TAP**: desistência, conclusão e permanência acumuladas (% dos ingressantes).\n- **Ano do curso**: tempo de acompanhamento da coorte (2015 = 1º ano, 2019 = 5º).\n- **Evasão anual**: perda de um único ano, medida no Censo.\n- **% e p.p.**: percentual é proporção; ponto percentual é diferença entre percentuais.\n- **Sem dados ≠ zero.** Vazio, "--" e "SC" são ausência de dado.\n- **EAD**: o município é o do polo, não o do aluno.\n- **Taxa média é ponderada** pelo nº de ingressantes (ou de matrículas).`, 6, 34)],
  ...METH.map(([t, d, f], i) => [md('md-m' + i, `#### ${t}\n${d}\n\n*${f}*`, 12, 12)]),
  [table('Qualidade · checagens automáticas da transformação', 'qualidade_checks', { raw: true, columns: ['etapa', 'checagem', 'valor', 'esperado', 'ok'], filters: [], page: 10 }, 'Resultado das checagens executadas na carga (taxa de junção, chaves duplicadas, volume por ano).')],
] });


// ───────────────────────── Filtros nativos ─────────────────────────
const tabId = id => 'TAB-' + id;
const FILTERS = [
  { key: 'coorte', name: 'Coorte (ano de ingresso)', ds: 'trajetoria', col: 'coorte', tabs: ['overview', 'p1', 'p2'], def: [2015], multi: false, required: true, exclude: [p2Hm] },
  { key: 'ano_curso', name: 'Ano do curso', ds: 'trajetoria', col: 'ano_curso', tabs: ['p2'], def: [4], multi: false, required: true },
  { key: 'rede', name: 'Rede', ds: 'trajetoria', col: 'rede', tabs: ['overview', 'p1', 'p2', 'p3', 'p4', 'p5', 'b2'] },
  { key: 'modalidade', name: 'Modalidade', ds: 'censo_curso', col: 'modalidade', tabs: ['p3', 'p4', 'p5', 'b2'] },
  { key: 'categoria_adm', name: 'Categoria administrativa', ds: 'censo_curso', col: 'categoria_adm', tabs: ['p3', 'p4', 'p5', 'b2'] },
  { key: 'area_cine', name: 'Área (CINE)', ds: 'trajetoria', col: 'area_cine', tabs: ['overview', 'p1', 'p2', 'p3', 'p4', 'b2'] },
  { key: 'rotulo_cine', name: 'Curso (rótulo CINE)', ds: 'trajetoria', col: 'rotulo_cine', tabs: ['p1', 'p3'] },
  { key: 'municipio', name: 'Município', ds: 'trajetoria', col: 'municipio', tabs: ['overview', 'p1', 'p2', 'p3', 'p4', 'p5', 'b1'] },
  { key: 'no_ies', name: 'Instituição', ds: 'trajetoria', col: 'no_ies', tabs: ['overview', 'p1', 'p2', 'p3', 'p4', 'p5', 'b2'] },
  { key: 'ano_cpc', name: 'Edição do CPC', ds: 'cpc_curso', col: 'ano_cpc', tabs: ['p4'] },
];
function nativeFilters() {
  return FILTERS.map(f => {
    const val = f.def;
    return {
      id: 'NATIVE_FILTER-' + uuid('nf' + f.key).slice(0, 12), name: f.name, filterType: 'filter_select', type: 'NATIVE_FILTER', description: '',
      controlValues: { enableEmptyFilter: !!f.required, defaultToFirstItem: false, multiSelect: f.multi !== false, searchAllOptions: false, inverseSelection: false },
      targets: [{ datasetUuid: ds(f.ds).uuid, column: { name: f.col } }],
      defaultDataMask: val ? { extraFormData: { filters: [{ col: f.col, op: 'IN', val }] }, filterState: { value: val }, ownState: {} } : { extraFormData: {}, filterState: {}, ownState: {} },
      cascadeParentIds: [], scope: { rootPath: f.tabs.map(tabId), excluded: f.exclude || [] },
    };
  });
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
      const items = Array.isArray(row) ? row : [row];
      const n = items.length;
      items.forEach(it => {
        if (typeof it === 'object' && it.md) {
          const w = n === 1 ? it.width : it.width;
          pos['MARKDOWN-' + it.id] = { type: 'MARKDOWN', id: 'MARKDOWN-' + it.id, children: [], parents: [...tp, rid], meta: { width: w, height: it.height, code: it.code } };
          pos[rid].children.push('MARKDOWN-' + it.id);
        } else {
          const ch = charts.find(c => c.id === it);
          const isKpi = ch.params.viz_type === 'big_number_total';
          const mdOnly = items.length === 1;
          pos['CHART-' + it] = { type: 'CHART', id: 'CHART-' + it, children: [], parents: [...tp, rid], meta: { width: widthsFor(n), height: isKpi ? 20 : (ch.params.viz_type === 'table' ? 48 : 52), chartId: it, uuid: uuid('chart' + ch.name), sliceName: ch.name } };
          pos[rid].children.push('CHART-' + it);
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
write('databases/Rota_do_Diploma_mart.yaml', { database_name: DB.name, sqlalchemy_uri: DB_URI, cache_timeout: null, expose_in_sqllab: true, allow_run_async: false, allow_ctas: false, allow_cvas: false, allow_dml: false, allow_file_upload: false, extra: { allows_virtual_table_explore: true }, uuid: DB.uuid, version: '1.0.0' });
for (const [k, d] of Object.entries(DATASETS)) {
  write(`datasets/Rota_do_Diploma_mart/${k}.yaml`, {
    table_name: k, main_dttm_col: null, description: d.desc, default_endpoint: null, offset: 0, cache_timeout: null, schema: 'mart', sql: null, params: null, template_params: null, filter_select_enabled: true, fetch_values_predicate: null, extra: null, normalize_columns: false, always_filter_main_dttm: false, uuid: d.uuid,
    metrics: d.metrics.map(x => ({ metric_name: x.name, verbose_name: x.verbose, metric_type: null, expression: x.expr, description: x.d || null, d3format: x.fmt, currency: null, extra: null, warning_text: null })),
    columns: d.cols.map(c => ({ column_name: c.n, verbose_name: c.d || null, is_dttm: false, is_active: true, type: c.t, advanced_data_type: null, groupby: true, filterable: true, expression: null, description: null, python_date_format: null, extra: null })),
    version: '1.0.0', database_uuid: DB.uuid,
  });
}
charts.forEach(c => {
  write(`charts/${c.name.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^A-Za-z0-9]+/g, '_')}_${c.id}.yaml`, { slice_name: c.name, description: c.desc || null, certified_by: null, certification_details: null, viz_type: c.params.viz_type, params: c.params, query_context: null, cache_timeout: null, uuid: uuid('chart' + c.name), version: '1.0.0', dataset_uuid: ds(c.ds).uuid });
});
const meta = {
  color_scheme: 'univag', label_colors: LABELS, shared_label_colors: {}, map_label_colors: {}, refresh_frequency: 0, timed_refresh_immune_slices: [], expanded_slices: {}, cross_filters_enabled: true, default_filters: '{}', filter_scopes: {}, chart_configuration: {},
  native_filter_configuration: nativeFilters(), global_chart_configuration: { scope: { rootPath: ['ROOT_ID'], excluded: [] }, chartsInScope: [] },
};
const css = `.dashboard-component-tabs .ant-tabs-tab-active .ant-tabs-tab-btn{color:#0066CC;font-weight:600}
.dashboard-markdown h3{color:#1A2B5E;margin-top:4px}
.dashboard-markdown blockquote{border-left:4px solid #0066CC;background:#EAF1FA;padding:6px 12px;color:#1A2B5E}
.dashboard-header .editable-title input, .dashboard-header .editable-title{color:#1A2B5E;font-weight:700}`;
write('dashboards/Rota_do_Diploma.yaml', { dashboard_title: 'Rota do Diploma · Mato Grosso', description: 'Trajetória e evasão no Ensino Superior de MT (INEP/IBGE). DataHack UNIVAG 2026.', css, slug: 'rota-do-diploma', certified_by: null, certification_details: null, published: true, uuid: uuid('dashboard'), position: buildPosition(), metadata: meta, version: '1.0.0' });

const zip = path.join(OUT, 'rota_do_diploma.zip');
fs.rmSync(zip, { force: true });
const TAR = path.join(process.env.SystemRoot || 'C:/Windows', 'System32', 'tar.exe');
cp.execFileSync(TAR, ['-a', '-c', '-f', 'rota_do_diploma.zip', ROOT], { cwd: OUT, stdio: 'inherit' });
console.log(`OK ${charts.length} gráficos · ${Object.keys(DATASETS).length} datasets · ${tabs.length} abas · ${FILTERS.length} filtros -> ${zip}${DEMO ? ' (DEMO)' : ''}`);
