.PHONY: test smoke lint clean

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

smoke:
	PYTHONPATH=src python3 -m album_assetizer --root . scan
	PYTHONPATH=src python3 -m album_assetizer --root . annotate
	PYTHONPATH=src python3 -m album_assetizer --root . export
	PYTHONPATH=src python3 -m album_assetizer --root . stats

lint:
	python3 -m py_compile $$(find src tests -name '*.py')

clean:
	rm -rf .album-assetizer/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
