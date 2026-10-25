# MooPet

MooPet é um projeto que cria uma vaca pet que anda pela tela, foge do mouse
e inclui várias outras features interativas.

Parte da linha TheMooProject

## Créditos

Os sprites não são meus: são do criador **moonrain479**, do projeto
**DesktopCow**. Você precisa baixá-los separadamente.

- Projeto original: [https://github.com/Moonrain479/DesktopCow/]
- Os sprites **não são distribuídos** neste repositório.

## Como usar

O MooPet é uma ferramenta comandada por um CLI. para usar com parâmetros diferentes você pode seguir a lista de parâmetros utilizáveis:

- ```--modo-irritante```: é uma configuração que adiciona features irritantes pra vaca
- ```--quantidade```: diz quantas vacas ele deve criar

### exemplos da CLI
todos esses comandos podem ser combinados entre si. aqui vão exemplos de combinações 

- Apocalipse de vacas(⚠️ AVISO: esse comando pode inutilizar a sessão gráfica, para resolver, basta matar o processo python em outro tty ou reiniciar.): ```python3 pet.py --quantidade 100 --modo-irritante```
- reunião de vacas(para criticar as regras rígidas dos sistemas wayland, elas não conseguem se mover.): ```python3 pet.py --quantidade 10```
- família de vacas(por que uma vaca sozinha fica entediada rápido): ```python3 pet.py --quantidade 5```
- família de vacas irritadas( uma família que não presta): ```python3 pet.py --quantidade 5 --modo-irritante```
- times de vacas rivais(elas aparentemente se odeiam): ```python3 pet.py --quantidade 5 & python3 pet.py --quantidade 5 --modo-irritante```
- irmãos vacas(que não são um certo encanador da Itália): ```python3 pet.py --quantidade 2```
- família de vacas com apenas uma vaca irritada(família perfeita com irmão casula chato): ```python3 pet.py --quantidade 4 & python3 pet.py --modo-irritante```
- Vaca que se multiplica(esse código pode travar o sistema por falta de recursos, tente matar o processo pelo tty e caso não funcione reinicie diretamente pela energia): ```n=1; while :; do for ((i=0;i<n;i++)); do python3 pet.py & done; ((n*=2)); sleep 1; done```

- Vaca irritada que se multiplica(⚠️ novamente, esse código pode travar o sistema por falta de recursos, tente matar o processo pelo tty e caso não funcione reinicie diretamente pela energia): ```n=1; while :; do for ((i=0;i<n;i++)); do python3 pet.py --modo-irritante & done; ((n*=2)); sleep 1; done```

## Como baixar

1. Baixe os sprites do projeto DesktopCow (link acima).
2. Baixe o arquivo pet.py do repositório atual.
3. Coloque os arquivos `.gif` na mesma pasta do `pet.py` baixado.
4. Rode:

   ```bash
   python3 pet.py
   ```
