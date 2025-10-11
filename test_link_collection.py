#!/usr/bin/env python3
"""
Test básico para validar o fluxo de coleta e parsing de links.
Este teste verifica que:
1. Links podem ser salvos na tabela links_coleta
2. Links duplicados não são inseridos novamente
3. Links podem ser recuperados como ativos
4. Links podem ser marcados como parseados (inativos)
5. TTL funciona corretamente
"""
from datetime import datetime, timedelta
from backend.db.database import SessionLocal
from backend.models.models import LinkColeta
from backend.modules.services.link_service import LinkService


def test_link_lifecycle():
    """Testa o ciclo de vida completo de um link."""
    db = SessionLocal()
    link_service = LinkService(db)
    
    print("=== Teste de Ciclo de Vida de Links ===\n")
    
    # 1. Salvar links
    print("1. Salvando links...")
    test_links = [
        {"url_base": "https://www.mercadolivre.com.br/produto-1"},
        {"url_base": "https://www.mercadolivre.com.br/produto-2"},
        {"url_base": "https://www.mercadolivre.com.br/produto-3"},
    ]
    inserted = link_service.save_links(test_links, source="mercadolivre")
    print(f"   ✓ Inseridos {inserted} novos links")
    assert inserted == 3, f"Esperava 3 links novos, mas inseriu {inserted}"
    
    # 2. Tentar salvar duplicados
    print("\n2. Tentando salvar links duplicados...")
    inserted = link_service.save_links(test_links, source="mercadolivre")
    print(f"   ✓ Inseridos {inserted} novos links (esperado: 0)")
    assert inserted == 0, f"Não deveria inserir duplicados, mas inseriu {inserted}"
    
    # 3. Recuperar links ativos
    print("\n3. Recuperando links ativos...")
    active_links = link_service.get_active_links(source="mercadolivre")
    print(f"   ✓ Encontrados {len(active_links)} links ativos")
    assert len(active_links) >= 3, f"Esperava pelo menos 3 links ativos, mas encontrou {len(active_links)}"
    
    # 4. Marcar um link como parseado
    print("\n4. Marcando link como parseado...")
    first_link = active_links[0]
    success = link_service.mark_as_parsed(first_link.id)
    print(f"   ✓ Link {first_link.id} marcado como parseado")
    assert success, "Falha ao marcar link como parseado"
    
    # Verificar que agora há menos links ativos
    active_links_after = link_service.get_active_links(source="mercadolivre")
    print(f"   ✓ Links ativos agora: {len(active_links_after)}")
    assert len(active_links_after) == len(active_links) - 1, "Link parseado ainda está ativo"
    
    # 5. Marcar um link como falho
    print("\n5. Marcando link como falho...")
    second_link = active_links[1]
    success = link_service.mark_as_failed(second_link.id, "Erro de teste")
    print(f"   ✓ Link {second_link.id} marcado como falho")
    assert success, "Falha ao marcar link como falho"
    
    # Verificar que o link ainda está ativo (para retry)
    db.expire_all()  # Refresh do cache
    link_after_fail = db.query(LinkColeta).filter(LinkColeta.id == second_link.id).first()
    print(f"   ✓ Link continua ativo: {link_after_fail.ativo}")
    print(f"   ✓ Tentativas: {link_after_fail.tentativas}")
    assert link_after_fail.ativo, "Link com falha deveria continuar ativo"
    assert link_after_fail.tentativas == 1, "Contador de tentativas não foi incrementado"
    
    # 6. Testar TTL
    print("\n6. Testando TTL (Time To Live)...")
    # Criar um link antigo manualmente
    old_link = LinkColeta(
        url="https://www.mercadolivre.com.br/produto-antigo",
        source="mercadolivre",
        ativo=True,
        criado_em=datetime.utcnow() - timedelta(hours=25)  # Mais de 24h atrás
    )
    db.add(old_link)
    db.commit()
    print(f"   ✓ Link antigo criado (ID: {old_link.id})")
    
    # Executar cleanup
    removed = link_service.cleanup_expired_links(ttl_hours=24)
    print(f"   ✓ Links expirados removidos: {removed}")
    assert removed >= 1, f"Esperava remover pelo menos 1 link expirado, mas removeu {removed}"
    
    # Verificar que o link antigo foi removido
    db.expire_all()
    old_link_after = db.query(LinkColeta).filter(LinkColeta.id == old_link.id).first()
    assert old_link_after is None, "Link expirado não foi removido"
    print(f"   ✓ Link antigo foi removido com sucesso")
    
    # Limpeza
    print("\n7. Limpando dados de teste...")
    for link in test_links:
        url = link["url_base"]
        db.query(LinkColeta).filter(
            LinkColeta.url == url,
            LinkColeta.source == "mercadolivre"
        ).delete()
    db.commit()
    db.close()
    
    print("\n=== ✓ Todos os testes passaram! ===")


if __name__ == "__main__":
    try:
        test_link_lifecycle()
    except AssertionError as e:
        print(f"\n✗ Teste falhou: {e}")
        exit(1)
    except Exception as e:
        print(f"\n✗ Erro inesperado: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
