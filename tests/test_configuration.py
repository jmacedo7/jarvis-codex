import tempfile
import unittest
from pathlib import Path

from security.configuration import atualizar_env, ler_env


class ConfiguracaoEnvTests(unittest.TestCase):
    def test_le_arquivo_sem_interpretar_comentarios(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / ".env"
            caminho.write_text(
                '# comentário\nexport ELEVENLABS_API_KEY="segredo-de-teste"\nJARVIS_VOZ=voz-123\n',
                encoding="utf-8",
            )
            valores = ler_env(caminho)
            self.assertEqual(valores["ELEVENLABS_API_KEY"], "segredo-de-teste")
            self.assertEqual(valores["JARVIS_VOZ"], "voz-123")
            self.assertNotIn("comentário", valores)

    def test_atualiza_voz_sem_apagar_chave_e_remove_duplicata(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / ".env"
            caminho.write_text(
                '# manter\nELEVENLABS_API_KEY=nao-alterar\nJARVIS_VOZ=antiga\nJARVIS_VOZ=duplicada\n',
                encoding="utf-8",
            )
            atualizar_env(caminho, {"JARVIS_VOZ": "nova", "JARVIS_VELOCIDADE_VOZ": "1.05"})
            valores = ler_env(caminho)
            texto = caminho.read_text(encoding="utf-8")
            self.assertEqual(valores["ELEVENLABS_API_KEY"], "nao-alterar")
            self.assertEqual(valores["JARVIS_VOZ"], "nova")
            self.assertEqual(valores["JARVIS_VELOCIDADE_VOZ"], "1.05")
            self.assertEqual(texto.count("JARVIS_VOZ="), 1)
            self.assertIn("# manter", texto)


if __name__ == "__main__":
    unittest.main()
