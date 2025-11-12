# Permisos IAM Requeridos para el Proyecto Mineria

## Resumen
Este documento lista los permisos IAM necesarios para desplegar y operar la infraestructura del proyecto de clasificación forestal con Sentinel-2.

## Contexto
El proyecto requiere crear recursos AWS mediante Terraform, incluyendo:
- Instancias EC2 para procesamiento de datos (scripts 01-05)
- Clusters EMR para entrenamiento con Spark (scripts 06-07)
- Buckets S3 para almacenamiento
- Roles y políticas IAM para permisos de servicios

## Usuario Actual
- **Usuario**: `arn:aws:iam::264483381923:user/maraosoc`
- **Cuenta**: `264483381923`
- **Limitación**: No tiene permisos para crear/modificar roles y políticas IAM

---

## Permisos IAM Requeridos

### 1. IAM - Gestión de Roles ⚠️ CRÍTICO
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:GetRole",
        "iam:ListRoles",
        "iam:UpdateRole",
        "iam:TagRole",
        "iam:UntagRole",
        "iam:UpdateAssumeRolePolicy"
      ],
      "Resource": [
        "arn:aws:iam::264483381923:role/mineria-*"
      ]
    }
  ]
}
```

**Justificación**: Necesario para crear roles de servicio para EC2 y EMR que permitan acceso a S3.

---

### 2. IAM - Gestión de Políticas ⚠️ CRÍTICO
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "iam:CreatePolicy",
        "iam:DeletePolicy",
        "iam:GetPolicy",
        "iam:GetPolicyVersion",
        "iam:ListPolicies",
        "iam:ListPolicyVersions",
        "iam:CreatePolicyVersion",
        "iam:DeletePolicyVersion",
        "iam:TagPolicy",
        "iam:UntagPolicy"
      ],
      "Resource": [
        "arn:aws:iam::264483381923:policy/mineria-*"
      ]
    }
  ]
}
```

**Justificación**: Crear políticas customizadas de acceso a S3 para EC2 y EMR.

---

### 3. IAM - Adjuntar Políticas ⚠️ CRÍTICO
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:ListAttachedRolePolicies",
        "iam:ListRolePolicies"
      ],
      "Resource": [
        "arn:aws:iam::264483381923:role/mineria-*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "iam:AttachRolePolicy"
      ],
      "Resource": [
        "arn:aws:iam::264483381923:role/mineria-*"
      ],
      "Condition": {
        "ArnLike": {
          "iam:PolicyARN": [
            "arn:aws:iam::aws:policy/service-role/AmazonElasticMapReduceRole",
            "arn:aws:iam::aws:policy/service-role/AmazonElasticMapReduceforEC2Role",
            "arn:aws:iam::264483381923:policy/mineria-*"
          ]
        }
      }
    }
  ]
}
```

**Justificación**: Vincular políticas AWS gestionadas (EMR) y customizadas a los roles creados.

---

### 4. IAM - Instance Profiles
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "iam:CreateInstanceProfile",
        "iam:DeleteInstanceProfile",
        "iam:GetInstanceProfile",
        "iam:ListInstanceProfiles",
        "iam:AddRoleToInstanceProfile",
        "iam:RemoveRoleFromInstanceProfile",
        "iam:TagInstanceProfile",
        "iam:UntagInstanceProfile"
      ],
      "Resource": [
        "arn:aws:iam::264483381923:instance-profile/mineria-*"
      ]
    }
  ]
}
```

**Justificación**: Los Instance Profiles permiten a las instancias EC2 asumir roles IAM.

---

### 5. IAM - Operaciones de Lectura (Opcionales pero Recomendadas)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "iam:GetUser",
        "iam:ListAttachedUserPolicies",
        "iam:ListUserPolicies",
        "iam:GetUserPolicy"
      ],
      "Resource": [
        "arn:aws:iam::264483381923:user/maraosoc"
      ]
    }
  ]
}
```

**Justificación**: Permite verificar permisos actuales y troubleshooting.

---

### 6. PassRole - Permisos Críticos
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": [
        "arn:aws:iam::264483381923:role/mineria-*"
      ],
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": [
            "ec2.amazonaws.com",
            "elasticmapreduce.amazonaws.com"
          ]
        }
      }
    }
  ]
}
```

**Justificación**: Permite a EC2 y EMR usar los roles IAM creados.

---

## Permisos Actuales (Ya Funcionando)

Estos permisos ya los tienes, ya que pudiste crear recursos S3 y de red:

### ✅ S3
- `s3:CreateBucket`
- `s3:DeleteBucket`
- `s3:ListBucket`
- `s3:GetObject`
- `s3:PutObject`
- `s3:DeleteObject`
- `s3:PutBucketPolicy`
- `s3:PutBucketVersioning`
- `s3:PutBucketPublicAccessBlock`
- `s3:PutLifecycleConfiguration`
- `s3:PutEncryptionConfiguration`

### ✅ EC2 - Redes y Seguridad
- `ec2:CreateSecurityGroup`
- `ec2:DeleteSecurityGroup`
- `ec2:AuthorizeSecurityGroupIngress`
- `ec2:AuthorizeSecurityGroupEgress`
- `ec2:RevokeSecurityGroupIngress`
- `ec2:RevokeSecurityGroupEgress`
- `ec2:DescribeVpcs`
- `ec2:DescribeSubnets`
- `ec2:DescribeSecurityGroups`

### ✅ EC2 - Instancias (Probablemente)
- `ec2:RunInstances`
- `ec2:TerminateInstances`
- `ec2:DescribeInstances`
- `ec2:DescribeImages`
- `ec2:DescribeKeyPairs`
- `ec2:CreateKeyPair`

### ✅ EMR (Probablemente)
- `elasticmapreduce:CreateCluster`
- `elasticmapreduce:TerminateCluster`
- `elasticmapreduce:DescribeCluster`

---

## Política IAM Completa Recomendada

Si tu administrador prefiere una política unificada, aquí está todo combinado:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "MineriaIAMRoleManagement",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:GetRole",
        "iam:ListRoles",
        "iam:UpdateRole",
        "iam:TagRole",
        "iam:UntagRole",
        "iam:UpdateAssumeRolePolicy"
      ],
      "Resource": "arn:aws:iam::264483381923:role/mineria-*"
    },
    {
      "Sid": "MineriaIAMPolicyManagement",
      "Effect": "Allow",
      "Action": [
        "iam:CreatePolicy",
        "iam:DeletePolicy",
        "iam:GetPolicy",
        "iam:GetPolicyVersion",
        "iam:ListPolicies",
        "iam:ListPolicyVersions",
        "iam:CreatePolicyVersion",
        "iam:DeletePolicyVersion",
        "iam:TagPolicy",
        "iam:UntagPolicy"
      ],
      "Resource": "arn:aws:iam::264483381923:policy/mineria-*"
    },
    {
      "Sid": "MineriaIAMPolicyAttachment",
      "Effect": "Allow",
      "Action": [
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:ListAttachedRolePolicies",
        "iam:ListRolePolicies"
      ],
      "Resource": "arn:aws:iam::264483381923:role/mineria-*"
    },
    {
      "Sid": "MineriaIAMInstanceProfile",
      "Effect": "Allow",
      "Action": [
        "iam:CreateInstanceProfile",
        "iam:DeleteInstanceProfile",
        "iam:GetInstanceProfile",
        "iam:ListInstanceProfiles",
        "iam:AddRoleToInstanceProfile",
        "iam:RemoveRoleFromInstanceProfile",
        "iam:TagInstanceProfile",
        "iam:UntagInstanceProfile"
      ],
      "Resource": "arn:aws:iam::264483381923:instance-profile/mineria-*"
    },
    {
      "Sid": "MineriaIAMPassRole",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::264483381923:role/mineria-*",
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": [
            "ec2.amazonaws.com",
            "elasticmapreduce.amazonaws.com"
          ]
        }
      }
    },
    {
      "Sid": "MineriaIAMReadOperations",
      "Effect": "Allow",
      "Action": [
        "iam:GetUser",
        "iam:ListAttachedUserPolicies",
        "iam:ListUserPolicies",
        "iam:GetUserPolicy"
      ],
      "Resource": "arn:aws:iam::264483381923:user/maraosoc"
    }
  ]
}
```

---

## Recursos IAM que Creará Terraform

Una vez tengas los permisos, Terraform creará automáticamente estos recursos:

### Para EC2:
1. **Rol**: `mineria-ec2-processing-role-dev`
   - Permite a EC2 asumir este rol
   
2. **Política**: `mineria-ec2-s3-access-dev`
   - Permisos: GetObject, PutObject, DeleteObject, ListBucket en `s3://mineria-project/*`
   
3. **Instance Profile**: `mineria-ec2-instance-profile-dev`
   - Vincula el rol a la instancia EC2

### Para EMR:
1. **Rol de Servicio**: `mineria-emr-service-role-dev`
   - Permite a EMR gestionar el cluster
   - Política adjunta: `AmazonElasticMapReduceRole` (AWS Managed)
   
2. **Rol EC2 para EMR**: `mineria-emr-ec2-role-dev`
   - Permite a nodos EMR acceder a recursos
   - Políticas: `AmazonElasticMapReduceforEC2Role` + `mineria-emr-s3-access-dev`
   
3. **Política S3**: `mineria-emr-s3-access-dev`
   - Permisos S3 para el cluster EMR
   
4. **Instance Profile EMR**: `mineria-emr-ec2-profile-dev`

---

## Justificación de Seguridad

### ✅ Principio de Least Privilege
- Todos los recursos tienen prefijo `mineria-*`, limitando el alcance
- PassRole restringido solo a servicios EC2 y EMR
- Sin permisos para modificar otros usuarios o roles del sistema

### ✅ Rastreabilidad
- Todos los recursos tienen tags: `Project=mineria`, `Environment=dev`
- Fácil auditoría con AWS CloudTrail

### ✅ Temporal
- Una vez creada la infraestructura, estos permisos pueden ser revocados
- Los roles creados permanecerán funcionales

---

## Cómo Solicitar a tu Administrador

### Email Template:

```
Asunto: Solicitud de Permisos IAM para Proyecto Mineria

Hola [Administrador],

Necesito permisos adicionales para desplegar infraestructura AWS con Terraform 
para el proyecto de clasificación forestal con datos Sentinel-2.

Recursos que necesito crear:
- Roles IAM para instancias EC2 y clusters EMR
- Políticas customizadas de acceso a S3
- Instance Profiles para vincular roles a instancias

Detalles de seguridad:
- Todos los recursos tienen prefijo "mineria-*" (alcance limitado)
- PassRole solo permitido para servicios EC2 y EMR
- Sin permisos sobre otros usuarios o roles existentes

La política IAM completa está documentada en:
docs/IAM_PERMISSIONS_REQUIRED.md

¿Podrías adjuntar la política "MineriaProjectIAM" a mi usuario maraosoc?

Gracias,
[Tu nombre]
```

---

## Alternativa Sin Permisos IAM

Si no es posible obtener estos permisos, hay una alternativa:

1. **Tu administrador crea los roles manualmente**
2. **Modifcamos Terraform** para usar roles existentes en lugar de crearlos
3. **Usas credenciales AWS CLI** en EC2 en lugar de Instance Profiles

Ver: `docs/AWS_SETUP.md` sección "Configuración Sin Permisos IAM"

---

## Verificación Post-Aprobación

Una vez otorgados los permisos, verifica con:

```bash
# Verificar permisos de roles
aws iam get-role --role-name mineria-ec2-processing-role-dev 2>&1

# Si no da error AccessDenied, tienes los permisos correctos

# Volver a intentar terraform apply
cd infrastructure
terraform plan
terraform apply
```

---

## Contacto
Para dudas sobre esta solicitud, contactar al equipo del proyecto Mineria.
