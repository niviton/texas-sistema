# 001 · Uma base única, em Django

**Data:** 05/10/2026 · **Situação:** aceita

## Contexto

Existiam dois sistemas: o Polaris (Django, certificados e veículos) e o Checklist Pro (React + Base44, checklist de equipamentos e termos). Manter os dois significa dois logins, dois bancos, dois padrões de PDF e dados da empresa fora de casa (no Base44).

## Decisão

O Polaris, em Django, é a base única. As funções do Checklist Pro são reconstruídas dentro dele, aproveitando as boas ideias de interface (um item por vez, barra inferior no celular, puxar para atualizar). O Base44 é desligado quando o Polaris cobrir 100% das funções e os dados forem importados.

## Consequências

- Dados, login e regras de acesso ficam sob controle da empresa.
- PDF TCB-OTB, e-mail e assinatura já existentes são reaproveitados.
- A interface do celular precisa ser cuidada no próprio Polaris (sem React).
- Exige hospedar o Polaris num servidor com HTTPS para uso em campo.
