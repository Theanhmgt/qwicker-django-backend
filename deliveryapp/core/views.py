import json
import secrets
import string
import vnpay
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction, IntegrityError
from django.db.models import Prefetch, Q, FilteredRelation
from django.db.models.functions import Now
from django.http import HttpResponse, JsonResponse
from rest_framework import viewsets, generics, permissions, parsers, status
from .models import *
from .paginator import *
from .perms import *
from .serializers import *
from rest_framework.decorators import action, permission_classes
from rest_framework.views import Response, APIView
from django.core.cache import cache
import cloudinary.uploader
from datetime import datetime
from django.utils import timezone
import random
from .ultils import *
from deliveryapp.celery import send_otp, send_apologia, send_congratulation, send_otp_to_reset_password


# Create your views here.
class BasicUserViewSet(viewsets.ViewSet, generics.CreateAPIView):
    queryset = BasicUser.objects.all()
    serializer_class = BasicUserSerializer
    parser_classes = [parsers.MultiPartParser, ]

    @action(methods=['get', 'put'], detail=False, url_path='current-user')
    def current_user(self, request):
        u = request.user
        if u.role == User.Roles.BASIC_USER:
            if request.method.__eq__('PUT'):
                for k, v in request.data.items():
                    setattr(u, k, v)
                u.save()
            return Response(BasicUserSerializer(u, context={'request': request}).data, status=status.HTTP_200_OK)
        else:
            return Response({}, status=status.HTTP_400_BAD_REQUEST)


class AccountViewSet(viewsets.ViewSet):
    queryset = User.objects.all()

    @action(methods=['POST'], detail=False, url_path='user/register')
    def register_user(self, request):
        try:
            data = request.data
            avatar = data.get('avatar')
            res = cloudinary.uploader.upload(avatar, folder='avatar_user/')
            new_user = User.objects.create_user(
                first_name=data.get('first_name'),
                last_name=data.get('last_name'),
                username=data.get('username'),
                email=data.get('email'),
                password=data.get('password'),
                avatar=res['secure_url'],
                role=BasicUser.Roles.BASIC_USER
            )
            return Response(data=BasicUserSerializer(new_user, context={'request': request}).data,
                            status=status.HTTP_201_CREATED)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({'error': 'Error creating user'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['POST'], detail=False, url_path='shipper/register')
    def register_shipper(self, request):
        try:
            with transaction.atomic():
                data = request.data
                avatar = data.get('avatar')
                res = cloudinary.uploader.upload(avatar, folder='avatar_user/')

                new_user = User.objects.create_user(
                    first_name=data.get('first_name'),
                    last_name=data.get('last_name'),
                    username=data.get('username'),
                    email=data.get('email'),
                    password=data.get('password'),
                    avatar=res['secure_url'],
                    role=BasicUser.Roles.SHIPPER,
                    verified=False
                )

                cmnd = data.get('cmnd')
                cmnd_file = cloudinary.uploader.upload(cmnd, folder='cmnd/')

                ShipperMore.objects.create(
                    user_id=new_user.id,
                    cmnd=cmnd_file['secure_url'],
                    vehicle_id=data.get('vehicle_id'),
                    vehicle_number=data.get('vehicle_number')

                )

                return Response(data=ShipperSerializer(new_user, context={'request': request}).data,
                                status=status.HTTP_201_CREATED)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({'error': 'Error creating user'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['post'], detail=False, url_path='change-password')
    def change_password(self, request):
        user = request.user
        if user.is_authenticated:
            old_password = request.data['old_password']
            new_password = request.data['new_password']
            if user.check_password(old_password):
                user.set_password(new_password)
                user.save()
                return Response({"change password success"}, status=status.HTTP_204_NO_CONTENT)
            else:
                return Response({'old_password is incorrect'}, status=status.HTTP_304_NOT_MODIFIED)
        else:
            return Response({'unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)

    @action(methods=['post'], detail=False, url_path='sent-otp')
    def sent_otp(self, request):
        email = request.data.get('email')

        if email and User.objects.filter(email=email).exists():
            otp = random.randint(1000, 9999)
            send_otp_to_reset_password.delay(email, otp)
            cache.set(email, str(otp), 60 * 3)
            return Response({}, status=status.HTTP_200_OK)
        else:
            return Response({f'{email} is not found '}, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['post'], detail=False, url_path='verify-email')
    def verify_email(self, request):
        if request.data.get('email') and request.data.get('otp'):
            email = request.data.get('email')
            otp = request.data.get('otp')
            cache_otp = cache.get(email)
            if cache_otp:
                if cache_otp == otp:
                    return Response({'Email is valid'}, status=status.HTTP_200_OK)
                else:
                    return Response({'incorrect otp'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({'otp time is expired'}, status=status.HTTP_204_NO_CONTENT)
        else:
            return Response({'Email and OTP are required'}, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['post'], detail=False, url_path='reset-password')
    def reset_password(self, request):
        email = request.data.get('email')
        new_password = request.data.get('new_password')
        if email and new_password:
            account = User.objects.filter(email=email).first()
            account.set_password(new_password)
            account.save()
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response({'Email and new password are required'}, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['post'], detail=False, url_path='check-account')
    def check_account(self, request):
        email = request.data.get('email')
        username = request.data.get('username')
        if email and username:
            account = User.objects.filter(username=username).first()
            if account:
                return JsonResponse({'mess': 'username already existed', 'code': '01'})
            account = User.objects.filter(email=email).first()
            if account:
                return JsonResponse({'mess': 'email already existed', 'code': '02'})
            return JsonResponse({'mess': ' info given valid', 'code': '00'})
        else:
            return Response({'Email and username are required'}, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['post'], detail=False, url_path='register/sent-otp')
    def sent_otp_to_new_email(self, request):
        email = request.data.get('email')
        username = request.data.get('username')
        if email and username:
            otp = random.randint(1000, 9999)
            send_otp.delay(email, otp, username)
            cache.set(email, str(otp), 60 * 3)
            return Response({}, status=status.HTTP_200_OK)
        else:
            return Response({'Email and username are required '}, status=status.HTTP_400_BAD_REQUEST)


class ShipperViewSet(viewsets.ViewSet, generics.RetrieveAPIView, generics.CreateAPIView):
    queryset = Shipper.objects.all()
    serializer_class = ShipperSerializer

    @action(methods=['get', 'put'], detail=False, url_path='current-user')
    def current_user(self, request):
        u = request.user
        if u.role == User.Roles.SHIPPER:
            if request.method.__eq__('PUT'):
                for k, v in request.data.items():
                    setattr(u, k, v)
                u.save()
            return Response(ShipperWithRatingSerializer(u, context={'request': request}).data,
                            status=status.HTTP_200_OK)
        else:
            return Response({}, status=status.HTTP_400_BAD_REQUEST)


class ShipperMoreViewSet(viewsets.ViewSet):
    queryset = ShipperMore.objects.all()
    serializer_class = ShipperMoreSerializer


class VehicleViewSet(viewsets.ViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer


class ProductViewSet(viewsets.ViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer


class ProductCategoryViewSet(viewsets.ViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer


class JobViewSet(viewsets.ViewSet, generics.CreateAPIView, generics.ListAPIView, generics.RetrieveAPIView):
    queryset = Job.objects.select_related('shipment', 'shipment__pick_up', 'shipment__delivery_address', 'product',
                                          'product__category', 'payment',
                                          'payment__method',
                                          'vehicle').order_by('-created_at')
    serializer_class = JobSerializer
    pagination_class = JobPaginator
    permission_classes = [BasicUserOwnerJob]

    def create(self, request, *args, **kwargs):
        data = request.data
        try:
            with transaction.atomic():
                shipment_data = json.loads(data.get('shipment'))
                pick_up = shipment_data.pop('pick_up')
                delivery_address = shipment_data.pop('delivery_address')
                # Address
                pick_up = Address.objects.create(**pick_up)
                # Address
                delivery_address = Address.objects.create(**delivery_address)
                # Shipment
                shipment_data['pick_up_id'] = pick_up.id
                shipment_data['delivery_address_id'] = delivery_address.id
                shipment = Shipment.objects.create(**shipment_data)

                # Product
                prod_data = json.loads(data.get('product'))
                res = cloudinary.uploader.upload(prod_data['image'], folder='product/')
                prod_data['image'] = res['secure_url']
                product = Product.objects.create(**prod_data)

                # Payment
                payment_data = json.loads(data.get('payment'))
                payment = Payment.objects.create(**payment_data)
                payment_method_id = int(payment_data['method_id'])
                cash_payment_method_id = PaymentMethod.objects.filter(name__icontains='Tiền mặt').first().id

                # Job
                job = json.loads(data.get('order'))
                job['poster_id'] = request.user.id
                job['product_id'] = product.id
                job['payment_id'] = payment.id
                job['shipment_id'] = shipment.id

                #
                job_instance = Job.objects.create(**job)
                if payment_method_id != cash_payment_method_id:
                    job_instance.status = Job.Status.WAITING_PAY
                    job_instance.save(update_fields=['status'])
                # delete data in redis db
                for key in cache.keys("job*"):
                    cache.delete(key)
                return Response(JobSerializer(job_instance, context={'request': request}).data,
                                status=status.HTTP_201_CREATED)
        except Exception as e:
            print(e)
            return Response(e, status=status.HTTP_400_BAD_REQUEST)

    def list(self, request, *args, **kwargs):
        query = self.get_queryset().filter(poster=request.user.id)
        job_status = request.query_params.get('status')
        kw = request.query_params.get('kw')
        if job_status:
            status_list = [s for s in job_status.split(',')]
            query = query.filter(status__in=status_list)
        if kw:
            query = query.filter(Q(shipment__pick_up__city__icontains=kw) | Q(shipment__pick_up__district__icontains=kw)
                                 | Q(shipment__pick_up__street__icontains=kw) | Q(
                shipment__pick_up__home_number__icontains=kw))
        query = self.paginate_queryset(query)
        jobs = self.serializer_class(data=query, many=True)
        jobs.is_valid()
        return Response(self.get_paginated_response(jobs.data), status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        query = self.get_queryset().filter(id=int(kwargs['pk']), poster=request.user.id).first()
        return Response(JobDetailSerializer(query).data, status=status.HTTP_200_OK)

    @action(methods=['post'], detail=True, url_path='assign')
    def assign(self, request, pk=None):
        shipper_id = request.data.get('shipper')
        if shipper_id:
            selected_shipper = Shipper.objects.get(pk=int(shipper_id))
            job = Job.objects.filter(id=pk).prefetch_related('auction_job')
            shippers = [auction.shipper for auction in job[0].auction_job.select_related('shipper').all()]
            rejected_shipper_emails = [s.email for s in shippers if s.id != int(shipper_id)]
            try:
                send_apologia.delay(rejected_shipper_emails, str(job[0].uuid.int)[:12])
                send_congratulation.delay(selected_shipper.email, selected_shipper.first_name)
            except Exception as e:
                return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            j = Job.objects.get(pk=pk)
            j.status = Job.Status.WAITING_SHIPPER
            j.winner_id = shipper_id
            j.save(update_fields=['status', 'winner_id'])
            return Response(JobSerializer(job[0], context={'request': request}).data, status=status.HTTP_200_OK)
        else:
            return Response({'shipper_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['get'], detail=True, url_path='list-shipper')
    def list_shipper(self, request, pk):
        user = request.user
        job = Job.objects.prefetch_related('auction_job').get(pk=pk)
        try:
            shippers = [auction.shipper for auction in job.auction_job.select_related('shipper').prefetch_related(
                Prefetch('shipper', queryset=Shipper.objects.prefetch_related('feedback_shipper'))).all()]
            feedback_query = [s.feedback_shipper.all() for s in shippers]
            if feedback_query:
                return Response(
                    ShipperWithRatingSerializer(shippers, many=True, context={'feedback': feedback_query[0]}).data,
                    status=status.HTTP_200_OK)
            else:
                return Response(ShipperWithRatingSerializer(shippers, many=True).data, status=status.HTTP_200_OK)
        except Job.DoesNotExist:
            return Response(status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['post'], detail=True, url_path='feedback')
    def feedback(self, request, pk=None):
        job = Job.objects.get(pk=pk)
        user = request.user
        if job.poster.id == user.id:
            try:
                feedback_data = request.data.dict()
                feedback_data['job_id'] = job.id
                feedback_data['user_id'] = request.user.id
                feedback = Feedback.objects.create(**feedback_data)
                return Response(FeedbackSerializer(feedback).data, status=status.HTTP_201_CREATED)
            except Exception as e:
                print(e)
                return Response(status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(status=status.HTTP_403_FORBIDDEN)


class ShipperJobViewSet(viewsets.ViewSet, generics.RetrieveAPIView):
    queryset = Job.objects.select_related('shipment', 'shipment__pick_up', 'shipment__delivery_address', 'product',
                                          'product__category', 'payment',
                                          'payment__method',
                                          'vehicle')
    serializer_class = JobSerializer
    pagination_class = JobPaginator
    permission_classes = [IsShipper]

    @action(methods=['get'], detail=False, url_path='find')
    def find(self, request):
        if len(request.query_params) == 1 and 'page' in request.query_params:
            page = int(request.query_params.get('page'))
            redis_key = f'job:page:{page}'
            redis_data = cache.get(redis_key)
            redis_expire_time = 60 * 5
            if redis_data:
                return Response(redis_data, status=status.HTTP_200_OK)
            else:
                query = self.get_queryset().filter(
                    ~Q(auction_job__shipper_id=request.user.id) & Q(status=Job.Status.FINDING_SHIPPER))
                query = self.paginate_queryset(query)
                jobs = self.serializer_class(query, many=True)
                data = self.get_paginated_response(jobs.data)
                cache.set(redis_key, data, redis_expire_time)
                return Response(data, status=status.HTTP_200_OK)
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, *args, **kwargs):
        try:
            query = Job.objects.get(pk=int(kwargs['pk']))
            data = JobDetailSerializer(query).data
            shipper_count = Auction.objects.filter(job__id=int(kwargs['pk'])).count()
            data['shipper_count'] = shipper_count
            return Response(data, status=status.HTTP_200_OK)
        except Job.DoesNotExist:
            return Response(status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['post'], detail=True, url_path='join')
    def join(self, request, pk=None):
        job = Job.objects.get(pk=pk)
        if job.status == Job.Status.FINDING_SHIPPER:
            try:
                Auction.objects.create(job_id=pk, shipper_id=request.user.id)
                return Response({"join successfully"}, status=status.HTTP_201_CREATED)
            except IntegrityError:
                return Response({"you've already joined this job"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"job is not in finding shipper state"}, status=status.HTTP_404_NOT_FOUND)

    @action(methods=['get'], detail=False, url_path='my-jobs')
    def my_jobs(self, request):
        query = self.get_queryset().filter(Q(auction_job__shipper_id=request.user.id))
        job_status = request.query_params.get('status')
        kw = request.query_params.get('kw')
        if job_status:
            status_list = [int(s) for s in job_status.split(',')]
            query = query.filter(status__in=status_list)
        if kw:
            query = query.filter(Q(shipment__pick_up__city__icontains=kw) | Q(shipment__pick_up__district__icontains=kw)
                                 | Q(shipment__pick_up__street__icontains=kw) | Q(
                shipment__pick_up__home_number__icontains=kw))
        query = self.paginate_queryset(query)
        jobs = self.serializer_class(data=query, many=True)
        jobs.is_valid()
        return Response(self.get_paginated_response(jobs.data), status=status.HTTP_200_OK)

    @action(methods=['post'], detail=True, url_path='complete')
    def complete(self, request, pk=None):
        job = Job.objects.filter(id=pk).select_related('payment', 'payment__method', 'shipment').first()
        if job.status == Job.Status.WAITING_SHIPPER:
            payment = job.payment
            if payment.payment_date is None:
                payment.payment_date = timezone.now()
                payment.amount = job.shipment.cost
                payment.save(update_fields=['payment_date', 'amount'])

            job.status = Job.Status.DONE
            job.save(update_fields=['status'])

            return Response({"complete!!!"}, status=status.HTTP_200_OK)
        else:
            return Response({"job is not in waiting shipper state"}, status=status.HTTP_400_BAD_REQUEST)


class ShipmentViewSet(viewsets.ViewSet):
    queryset = Shipment.objects.all()
    serializer_class = ShipmentSerializer


class AddressViewSet(viewsets.ViewSet):
    queryset = Address.objects.all()
    serializer_class = AddressSerializer


class PaymentViewSet(viewsets.ViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [IsBasicUser]

    @action(methods=['post'], detail=True, url_path='checkout')
    def checkout(self, request, pk=None):
        try:
            job = Job.objects.filter(id=int(request.data.get('order_id'))).select_related('shipment').first()
            payment = Payment.objects.get(pk=pk)
            job.status = Job.Status.FINDING_SHIPPER
            job.save(update_fields=['status'])

            payment.amount = job.shipment.cost
            payment.payment_date = timezone.now()
            payment.save(update_fields=['amount', 'payment_date'])
            return Response({}, status=status.HTTP_200_OK)
        except Payment.DoesNotExist or Job.DoesNotExist:
            return Response({}, status=status.HTTP_400_BAD_REQUEST)


class PaymentMethodViewSet(viewsets.ViewSet):
    queryset = PaymentMethod.objects.all()
    serializer_class = PaymentMethodSerializer


class AuctionViewSet(viewsets.ViewSet, generics.CreateAPIView):
    queryset = Auction.objects.all()
    serializer_class = AuctionSerializer

    def get_permissions(self):
        if self.action in ['create']:
            self.permission_classes = [IsShipper]
        return super(AuctionViewSet, self).get_permissions()

    def create(self, request, *args, **kwargs):
        job = request.data.get('job')
        shipper = request.data.get('shipper')
        if job and shipper is not None:
            try:
                a = Auction.objects.create(job_id=job, shipper_id=shipper)
                return Response(AuctionSerializer(a).data, status=status.HTTP_201_CREATED)
            except IntegrityError:
                return Response(data={'error_msg': "job or shipper does not exist!"},
                                status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data={'error_msg': "Job and shipper are required!!!"}, status=status.HTTP_400_BAD_REQUEST)


class FeedbackViewSet(viewsets.ViewSet, generics.ListAPIView):
    queryset = Feedback.objects.select_related('user', 'job').order_by('-created_at')
    serializer_class = FeedbackSerializer
    pagination_class = FeedbackPaginator
    permission_classes = [IsBasicUser]

    def list(self, request, *args, **kwargs):
        shipper_id = request.query_params.get('shipper')
        query = self.get_queryset()
        if shipper_id:
            query = query.filter(shipper_id=shipper_id)

        query_paginate = self.paginate_queryset(query)
        feedback = self.serializer_class(query_paginate, many=True)
        return Response(self.get_paginated_response(feedback.data), status=status.HTTP_200_OK)

    @action(methods=['get'], detail=False, url_path='my-feedback')
    def my_feedback(self, request):
        orderId = request.query_params.get('orderId')
        if orderId:
            feedback = Feedback.objects.filter(job_id=int(orderId)).first()
            if feedback:
                return Response(self.serializer_class(feedback).data, status=status.HTTP_200_OK)
            else:
                return Response({}, status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST)


class CouponViewSet(viewsets.ViewSet):
    queryset = Coupon.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    @action(methods=['post'], detail=False, url_path='my-coupon')
    def my_feedback(self, request):
        key = request.data.get('key')
        if key:
            coupon = Coupon.objects.filter(key=key)
            if coupon.exists():
                coupon = coupon.filter(end_at__gt=Now())
                if coupon.exists():
                    coupon = coupon.first()
                    return JsonResponse(
                        {'mess': 'The coupon is still valid.', 'code': '01', 'discount': coupon.percen_discount},
                        encoder=DjangoJSONEncoder)
                else:
                    return JsonResponse({'mess': 'The object has expired', 'code': '02'})
            else:
                return JsonResponse({'mess': 'coupon not found', 'code': '00'})
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST)
