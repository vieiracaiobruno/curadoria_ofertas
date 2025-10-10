#!/usr/bin/env python3
"""
Integration test for the complete link collection and parsing flow.
Simulates the flow without actual Selenium/network operations.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from backend.db.database import SessionLocal
from backend.models.models import LinkColeta
from backend.modules.services.link_collector_service import LinkCollectorService
from backend.modules.services.link_parser import LinkParser


def simulate_collector_output():
    """Simulate what MLCollector.run_collection() would return."""
    return [
        {"url_base": "https://mercadolivre.com.br/produto-a", "source": "mercadolivre"},
        {"url_base": "https://mercadolivre.com.br/produto-b", "source": "mercadolivre"},
        {"url_base": "https://mercadolivre.com.br/produto-c", "source": "mercadolivre"},
    ]


def simulate_parser_function(link, client):
    """Simulate what MLParser.parse() would return."""
    # Mock parsed data
    return {
        "source": link.source,
        "url_base": link.url,
        "id_product": f"MLB{hash(link.url) % 100000}",
        "seller_id": "12345",
        "store_name": "Test Store",
        "preco_original": 100.0,
        "preco_oferta": 80.0,
        "desconto": 20.0,
        "nome_produto": f"Product from {link.url[:30]}",
        "imagem_url": "https://example.com/image.jpg",
        "seller_score": 5,
        "ganho_real": 10.0,
        "url_afiliado_curta": "https://short.link/abc"
    }


def test_complete_flow():
    """Test the complete flow: collect → save → parse → process."""
    print("=" * 70)
    print("INTEGRATION TEST: Complete Link Collection & Parsing Flow")
    print("=" * 70)
    
    db = SessionLocal()
    
    try:
        # Phase 1: Collection (simulated)
        print("\n[Phase 1] Collecting links...")
        links = simulate_collector_output()
        print(f"✓ Collected {len(links)} links")
        
        # Phase 2: Save to database
        print("\n[Phase 2] Saving links to database...")
        link_service = LinkCollectorService(db)
        save_stats = link_service.save_links(links)
        print(f"✓ Saved links - Inserted: {save_stats['inserted']}, Duplicates: {save_stats['duplicates']}")
        
        # Phase 3: Parse links
        print("\n[Phase 3] Parsing links from database...")
        parser = LinkParser(db)
        
        # Cleanup expired links
        parser.cleanup_expired_links()
        
        # Get pending links
        pending_links = parser.get_pending_links()
        print(f"✓ Found {len(pending_links)} pending links")
        
        if pending_links:
            # Parse in parallel (simulated)
            print(f"✓ Starting parallel parsing...")
            
            # For testing, we'll simulate the parser without actually running parallel threads
            # In production, this would be: results = parser.parse_links_parallel(pending_links, simulate_parser_function)
            results = []
            for link in pending_links:
                try:
                    data = simulate_parser_function(link, None)
                    results.append(data)
                    parser.mark_link_processed(link.id, success=True)
                except Exception as e:
                    print(f"  ! Failed to parse {link.url}: {e}")
                    parser.mark_link_processed(link.id, success=False)
            
            print(f"✓ Parsed {len(results)} items successfully")
            
            # Phase 4: Verify results
            print("\n[Phase 4] Verifying results...")
            
            # Check that links were marked as processed
            still_active = db.query(LinkColeta).filter(LinkColeta.ativo == True).count()
            processed = db.query(LinkColeta).filter(LinkColeta.ativo == False).count()
            
            print(f"✓ Links processed: {processed}")
            print(f"✓ Links still active: {still_active}")
            
            # Show sample parsed data
            if results:
                print(f"\n✓ Sample parsed data:")
                sample = results[0]
                print(f"  - Product: {sample['nome_produto']}")
                print(f"  - Price: R$ {sample['preco_oferta']} (was R$ {sample['preco_original']})")
                print(f"  - Discount: {sample['desconto']}%")
                print(f"  - Store: {sample['store_name']}")
        
        # Phase 5: Test retry flow
        print("\n[Phase 5] Testing retry flow...")
        
        # Add a new link and mark it as failed
        retry_link = [{"url_base": "https://mercadolivre.com.br/retry-test", "source": "mercadolivre"}]
        link_service2 = LinkCollectorService(db)
        link_service2.save_links(retry_link)
        
        # Get the link and mark as failed
        retry_link_obj = db.query(LinkColeta).filter(
            LinkColeta.url == "https://mercadolivre.com.br/retry-test"
        ).first()
        
        if retry_link_obj:
            print(f"✓ Created retry test link (ID: {retry_link_obj.id})")
            parser.mark_link_processed(retry_link_obj.id, success=False)
            
            # Verify it's still active
            db.expire_all()
            retry_link_obj = db.query(LinkColeta).filter(LinkColeta.id == retry_link_obj.id).first()
            if retry_link_obj.ativo and retry_link_obj.tentativas > 0:
                print(f"✓ Link still active for retry (attempts: {retry_link_obj.tentativas})")
            else:
                print(f"✗ Failed: Link should be active with attempts > 0")
                return False
        
        print("\n" + "=" * 70)
        print("✓ INTEGRATION TEST PASSED")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n✗ INTEGRATION TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_flow_with_duplicates():
    """Test that running the flow multiple times handles duplicates correctly."""
    print("\n" + "=" * 70)
    print("INTEGRATION TEST: Multiple Runs with Duplicates")
    print("=" * 70)
    
    db = SessionLocal()
    
    try:
        # Simulate running the collector twice with same URLs
        links = [
            {"url_base": "https://mercadolivre.com.br/duplicate-test-1", "source": "mercadolivre"},
            {"url_base": "https://mercadolivre.com.br/duplicate-test-2", "source": "mercadolivre"},
        ]
        
        print("\n[Run 1] First collection run...")
        service1 = LinkCollectorService(db)
        stats1 = service1.save_links(links)
        print(f"✓ Inserted: {stats1['inserted']}, Duplicates: {stats1['duplicates']}")
        
        print("\n[Run 2] Second collection run (same URLs)...")
        service2 = LinkCollectorService(db)
        stats2 = service2.save_links(links)
        print(f"✓ Inserted: {stats2['inserted']}, Duplicates: {stats2['duplicates']}")
        
        if stats1['inserted'] > 0 and stats2['duplicates'] == stats1['inserted']:
            print("\n✓ Duplicate handling works correctly!")
            return True
        else:
            print(f"\n✗ Failed: Expected duplicates to match first run insertions")
            return False
            
    except Exception as e:
        print(f"\n✗ INTEGRATION TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def main():
    print("\n" + "=" * 70)
    print("INTEGRATION TESTS FOR LINK COLLECTION & PARSING")
    print("=" * 70 + "\n")
    
    results = []
    
    results.append(("Complete Flow", test_complete_flow()))
    results.append(("Duplicate Handling", test_flow_with_duplicates()))
    
    # Summary
    print("\n" + "=" * 70)
    print("INTEGRATION TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    print("=" * 70 + "\n")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
