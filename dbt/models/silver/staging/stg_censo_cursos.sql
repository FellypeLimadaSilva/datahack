with versao as (
    {{ dh_latest_partition(source('bronze', 'censo_cursos'), 'nu_ano_censo') }}
)

select
    {{ dh_to_int('nu_ano_censo') }}::int as nu_ano_censo,
    {{ dh_clean_text('co_curso') }}::text as co_curso,
    {{ dh_clean_text('co_ies') }}::text as co_ies,
    {{ dh_clean_text('no_curso') }}::text as no_curso,
    {{ dh_clean_text('co_municipio') }}::text as co_municipio,
    {{ dh_clean_text('no_municipio') }}::text as no_municipio,
    {{ dh_clean_text('sg_uf') }}::text as sg_uf,
    {{ dh_to_int('tp_rede') }}::int as tp_rede,
    (case {{ dh_to_int('tp_rede') }} when 1 then 'Pública' when 2 then 'Privada' end)::text as rede,
    {{ dh_to_int('tp_categoria_administrativa') }}::int as tp_categoria_administrativa,
    {{ dh_to_int('tp_modalidade_ensino') }}::int as tp_modalidade_ensino,
    {{ dh_modalidade(dh_to_int('tp_modalidade_ensino')) }}::text as modalidade,
    {{ dh_to_int('tp_nivel_academico') }}::int as tp_nivel_academico,
    {{ dh_to_int('tp_grau_academico') }}::int as tp_grau_academico,
    {{ dh_clean_text('co_cine_area_geral') }}::text as co_cine_area_geral,
    {{ dh_clean_text('no_cine_area_geral') }}::text as no_cine_area_geral,
    {{ dh_to_int('qt_vg_total') }}::bigint as nu_vagas,
    {{ dh_to_int('qt_inscrito_total') }}::bigint as qt_inscrito,
    {{ dh_to_int('qt_ing') }}::bigint as qt_ing,
    {{ dh_to_int('qt_mat') }}::bigint as qt_mat,
    {{ dh_to_int('qt_conc') }}::bigint as qt_conc,
    {{ dh_to_int('qt_sit_trancada') }}::bigint as qt_sit_trancada,
    {{ dh_to_int('qt_sit_desvinculado') }}::bigint as qt_sit_desvinculado,
    {{ dh_to_int('qt_sit_transferido') }}::bigint as qt_sit_transferido,
    {{ dh_to_int('qt_sit_falecido') }}::bigint as qt_sit_falecido,
    {{ dh_to_int('qt_ing_fies') }}::bigint as qt_ing_fies,
    {{ dh_to_int('qt_ing_prounii') }}::bigint as qt_ing_prouni_integral,
    {{ dh_to_int('qt_ing_prounip') }}::bigint as qt_ing_prouni_parcial,
    {{ dh_to_int('qt_mat_fies') }}::bigint as qt_mat_fies,
    {{ dh_to_int('qt_mat_prounii') }}::bigint as qt_mat_prouni_integral,
    {{ dh_to_int('qt_mat_prounip') }}::bigint as qt_mat_prouni_parcial,
    _dh_source_file::text as arquivo_origem
from versao
